"""The search index's life cycle (data-dictionary/PRDs/009-search-settings Requirement 9-15).

The search index is the engine (``app.services.analysis.pipeline.Engine``) the backend process
keeps in memory: column features, the BM25 word index, the topic index and the term expansion. It
is never stored; it is built from PostgreSQL when the process starts and again whenever its
inputs change. The backend runs one replica (Decision 4), so this process's engine is the only
one.

Every change of the search data (a dictionary import, a term or stopword list, settings, a manual
rebuild) goes through one change queue: one change at a time, at most 20 seconds of waiting
(``503 search_change_busy``). A change reads the current inputs from one consistent snapshot,
applies itself in memory, builds the new engine beside the serving one and only then writes, in
one transaction; the new engine serves after the write ("önce kur, sonra yaz"). A failure in the
build or the write leaves the database and the serving engine as they were and answers ``500
search_index_build_failed``. A started change finishes even when its client goes away. Builds take
no analysis lock: an analysis keeps the engine it started with.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import telemetry
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.infrastructure.repositories.search_setting_repository import (
    SearchSettingRepository,
)
from app.services.analysis.pipeline import Engine, Resources
from app.services.search_inputs import (
    InputIdentity,
    SearchInputs,
    platform_tenant_id,
    read_identity,
    read_inputs,
)
from app.services.search_settings_schema import (
    FIELDS,
    SettingEffect,
    SettingValueInvalid,
    check_value,
    engine_settings,
)

logger = logging.getLogger("app.search")

QUEUE_TIMEOUT_SECONDS = 20.0
DATABASE_POLL_SECONDS = 1.0
# The settings whose values are inside the word index (Requirement 1: effect "indeks").
WORD_INDEX_KEYS = tuple(key for key, f in FIELDS.items() if f.effect is SettingEffect.REINDEX)


class IndexTrigger(StrEnum):
    STARTUP = "startup"
    DICTIONARY = "dictionary"
    TERMS = "terms"
    STOPWORDS = "stopwords"
    SETTINGS = "settings"
    MANUAL = "manual"


class IndexState(StrEnum):
    BUILDING = "building"
    READY = "ready"
    STALE = "stale"


class SearchChangeBusy(Exception):
    """The change waited longer than the queue allows; nothing was written."""


class SearchIndexBuildFailed(Exception):
    """The build or the write failed; nothing was written and the serving engine stays."""


class SearchIndexNotReady(Exception):
    """No engine serves yet: the first build after the start has not finished."""


def search_change_busy() -> ApplicationError:
    return ApplicationError(
        503,
        "search_change_busy",
        "Başka bir değişiklik uygulanıyor; biraz sonra yeniden deneyin.",
        headers={"Retry-After": "5"},
    )


def search_index_build_failed() -> ApplicationError:
    return ApplicationError(
        500,
        "search_index_build_failed",
        "Arama indeksi kurulamadı; değişiklik kaydedilmedi.",
    )


@dataclass(frozen=True, slots=True)
class ServingEngine:
    engine: Engine
    identity: InputIdentity
    settings_values: dict[str, Any]
    built_at: datetime
    build_ms: int
    trigger: IndexTrigger


@dataclass(frozen=True, slots=True)
class ChangeMark:
    trigger: IndexTrigger
    at: datetime


@dataclass(frozen=True, slots=True)
class IndexStatus:
    state: IndexState
    stale_inputs: list[str]
    columns: int
    objects: int
    dictionary_version: str
    built_at: datetime | None
    build_ms: int | None
    trigger: IndexTrigger | None
    running: ChangeMark | None
    last_failure: ChangeMark | None


@dataclass(slots=True)
class ChangePlan:
    """What a change does once its turn has come.

    ``inputs`` are the new engine's inputs (``None``: no build); ``write`` writes the change in the
    given session, whose transaction the queue commits (``None``: nothing to write); ``result``
    is handed back to the caller. A plan with neither changes nothing.
    """

    inputs: SearchInputs | None = None
    write: Callable[[AsyncSession], Awaitable[None]] | None = None
    result: Any = None


Planner = Callable[[SearchInputs, ServingEngine | None], Awaitable[ChangePlan]]


@dataclass(frozen=True, slots=True)
class ChangeOutcome:
    result: Any
    elapsed_ms: int
    built: bool


def _keeps_word_index(
    serving: ServingEngine | None, inputs: SearchInputs, trigger: IndexTrigger
) -> bool:
    """Whether the new engine may take the serving engine's BM25 index (Requirement 13)."""

    if serving is None or trigger in (IndexTrigger.STARTUP, IndexTrigger.MANUAL):
        return False
    return (
        serving.identity.dictionary == inputs.identity.dictionary
        and serving.identity.stopwords == inputs.identity.stopwords
        and all(serving.settings_values[k] == inputs.settings_values[k] for k in WORD_INDEX_KEYS)
    )


def build_engine(
    inputs: SearchInputs, serving: ServingEngine | None, trigger: IndexTrigger
) -> Engine:
    """A new engine from ``inputs``; the unchanged word index is reused, never recomputed
    differently: the result is the engine built from scratch with the same inputs."""

    bm25 = None
    if serving is not None and _keeps_word_index(serving, inputs, trigger):
        bm25 = serving.engine.bm25
    return Engine(
        inputs.dictionary,
        engine_settings(inputs.settings_values),
        Resources(list(inputs.term_groups), inputs.stopwords),
        bm25=bm25,
    )


def exit_process() -> None:
    """Stop the process with a non-zero exit code (Requirement 5 and 10)."""

    for handler in logging.getLogger().handlers:
        handler.flush()
    os._exit(1)


def _error_type(error: BaseException) -> str:
    return type(error).__name__


class SearchIndex:
    """The process's single engine and its change queue."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        queue_timeout: float = QUEUE_TIMEOUT_SECONDS,
        builder: Callable[
            [SearchInputs, ServingEngine | None, IndexTrigger], Engine
        ] = build_engine,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session_factory = session_factory
        self._queue_timeout = queue_timeout
        self._builder = builder
        self._clock = clock
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._tenant_id: int | None = None
        self._stale_reported: set[tuple[InputIdentity, InputIdentity]] = set()
        self.serving: ServingEngine | None = None
        self.running: ChangeMark | None = None
        self.last_failure: ChangeMark | None = None

    # ------------------------------------------------------------------ reading

    def engine(self) -> Engine:
        """The serving engine; an analysis keeps the one it gets for its whole run."""

        if self.serving is None:
            raise SearchIndexNotReady
        return self.serving.engine

    def settings_values(self) -> dict[str, Any]:
        """The serving engine's settings, the single read for other capabilities
        (Requirement 2); not the database's values."""

        if self.serving is None:
            raise SearchIndexNotReady
        return dict(self.serving.settings_values)

    @property
    def is_serving(self) -> bool:
        return self.serving is not None

    async def tenant_id(self) -> int:
        if self._tenant_id is None:
            async with self._session_factory() as session:
                self._tenant_id = await platform_tenant_id(session)
        return self._tenant_id

    async def status(self) -> IndexStatus:
        serving = self.serving
        running = self.running
        stale: list[str] = []
        if serving is None or running is not None:
            state = IndexState.BUILDING
        else:
            current = await read_identity(self._session_factory, await self.tenant_id())
            stale = serving.identity.differences(current)
            state = IndexState.STALE if stale else IndexState.READY
            pair = (serving.identity, current)
            if stale and pair not in self._stale_reported:
                self._stale_reported.add(pair)
                log_event(logger, "search_index.stale_detected", inputs=",".join(stale))
            telemetry.set_search_index_ready(state is IndexState.READY)
        engine = serving.engine if serving else None
        return IndexStatus(
            state=state,
            stale_inputs=stale,
            columns=len(engine.dictionary.columns) if engine else 0,
            objects=len(engine.objects) if engine else 0,
            dictionary_version=engine.dictionary.version if engine else "",
            built_at=serving.built_at if serving else None,
            build_ms=serving.build_ms if serving else None,
            trigger=serving.trigger if serving else None,
            running=running,
            last_failure=self.last_failure,
        )

    # ------------------------------------------------------------------ building

    async def _build(
        self, trigger: IndexTrigger, inputs: SearchInputs, serving: ServingEngine | None
    ) -> ServingEngine:
        started = perf_counter()
        with telemetry.search_index_build_span(trigger) as record:
            try:
                engine = await asyncio.to_thread(self._builder, inputs, serving, trigger)
            except Exception as error:
                log_event(
                    logger,
                    "search_index.build",
                    trigger=trigger.value,
                    outcome="failed",
                    duration_ms=round((perf_counter() - started) * 1000),
                    error_type=_error_type(error),
                )
                raise SearchIndexBuildFailed from error
            record.outcome = "ok"
            record.columns = len(engine.dictionary.columns)
            record.objects = len(engine.objects)
        build_ms = round((perf_counter() - started) * 1000)
        log_event(
            logger,
            "search_index.build",
            trigger=trigger.value,
            outcome="ok",
            duration_ms=build_ms,
            columns=len(engine.dictionary.columns),
            objects=len(engine.objects),
        )
        return ServingEngine(
            engine=engine,
            identity=inputs.identity,
            settings_values=dict(inputs.settings_values),
            built_at=self._clock(),
            build_ms=build_ms,
            trigger=trigger,
        )

    def _serve(self, serving: ServingEngine) -> None:
        self.serving = serving
        dictionary = serving.engine.dictionary
        telemetry.set_active_dictionary(len(dictionary.columns), len(dictionary.object_keys))
        telemetry.set_search_index_ready(True)

    async def _acquire(self, trigger: IndexTrigger) -> None:
        try:
            async with asyncio.timeout(self._queue_timeout):
                await self._lock.acquire()
        except TimeoutError:
            log_event(logger, "search_change.busy", trigger=trigger.value)
            telemetry.record_search_change(trigger, "busy")
            raise SearchChangeBusy from None

    # ------------------------------------------------------------------ start

    async def run_startup(
        self,
        database_ready: Callable[[], Awaitable[bool]],
        on_fatal: Callable[[], None] = exit_process,
    ) -> None:
        """Requirement 10: once the database is ready, check the stored settings (Requirement 5)
        and build the first engine. Changes wait in the queue until then; a stored value off
        the schema or a failed first build stops the process."""

        await self._lock.acquire()
        self.running = ChangeMark(IndexTrigger.STARTUP, self._clock())
        try:
            while not await database_ready():
                await asyncio.sleep(DATABASE_POLL_SECONDS)
            try:
                tenant_id = await self.tenant_id()
                if not await self._stored_settings_valid(tenant_id):
                    on_fatal()
                    return
                inputs = await read_inputs(self._session_factory, tenant_id)
                if not inputs.identity.dictionary:
                    log_event(logger, "dictionary.empty")
                serving = await self._build(IndexTrigger.STARTUP, inputs, None)
            except Exception as error:  # noqa: BLE001 - any failure of the first build is fatal
                if not isinstance(error, SearchIndexBuildFailed):
                    log_event(
                        logger,
                        "search_index.build",
                        trigger=IndexTrigger.STARTUP.value,
                        outcome="failed",
                        error_type=_error_type(error),
                    )
                self.last_failure = ChangeMark(IndexTrigger.STARTUP, self._clock())
                on_fatal()
                return
            self._serve(serving)
        finally:
            self.running = None
            self._lock.release()

    async def _stored_settings_valid(self, tenant_id: int) -> bool:
        async with self._session_factory() as session:
            stored = await SearchSettingRepository(session).stored(tenant_id)
        valid = True
        for key, value in stored.items():
            try:
                check_value(key, value)
            except SettingValueInvalid as invalid:
                valid = False
                log_event(
                    logger,
                    "search_settings.startup_invalid",
                    key=key,
                    reason=invalid.reason.value,
                )
        return valid

    # ------------------------------------------------------------------ changes

    async def change(self, trigger: IndexTrigger, planner: Planner) -> ChangeOutcome:
        """Run one change through the queue; it completes even if the caller is cancelled."""

        task = asyncio.create_task(self._change(trigger, planner))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return await asyncio.shield(task)

    async def rebuild(self) -> ChangeOutcome:
        """Requirement 14: the engine from the current inputs, rebuilt even when unchanged."""

        async def plan(inputs: SearchInputs, _serving: ServingEngine | None) -> ChangePlan:
            return ChangePlan(inputs=inputs)

        return await self.change(IndexTrigger.MANUAL, plan)

    async def _change(self, trigger: IndexTrigger, planner: Planner) -> ChangeOutcome:
        started = perf_counter()
        await self._acquire(trigger)
        self.running = ChangeMark(trigger, self._clock())
        try:
            with telemetry.search_change_span(trigger) as record:
                try:
                    inputs = await read_inputs(self._session_factory, await self.tenant_id())
                    plan = await planner(inputs, self.serving)
                    if plan.inputs is None and plan.write is None:
                        record.outcome = "unchanged"
                        return ChangeOutcome(plan.result, _elapsed(started), built=False)
                    serving = (
                        await self._build(trigger, plan.inputs, self.serving)
                        if plan.inputs is not None
                        else None
                    )
                    if plan.write is not None:
                        async with self._session_factory() as session:
                            await plan.write(session)
                            await session.commit()
                except ApplicationError:
                    raise  # a deliberate refusal, such as a dictionary import in progress
                except Exception as error:
                    self.last_failure = ChangeMark(trigger, self._clock())
                    raise SearchIndexBuildFailed from error
                if serving is not None:
                    self._serve(serving)
                record.outcome = "applied"
                return ChangeOutcome(plan.result, _elapsed(started), built=serving is not None)
        finally:
            self.running = None
            self._lock.release()


def _elapsed(started: float) -> int:
    return round((perf_counter() - started) * 1000)
