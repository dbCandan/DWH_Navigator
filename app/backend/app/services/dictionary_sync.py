"""Dictionary update and rollback runs (011-dictionary-sync).

A run lives in this process: accepted at once, then read, compared, filled and written in the
background. One partial unique index allows one running run per tenant. The active dictionary
changes only through the search index's change queue, so a failed read, model or build leaves it as
it was. No table, column, description or model text reaches a log line.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.secret_cipher import SecretCipher, SecretUnreadable, decode_encryption_key
from app.domain.dictionary import (
    MAX_KEPT_WARNINGS,
    VERSION_RETENTION_DAYS,
    DictionaryStatus,
    ImportChannel,
)
from app.domain.dictionary_source import (
    DictionarySourcePort,
    SourceConnection,
    SourceInvalid,
    SourceUnavailable,
    TargetUnavailable,
)
from app.domain.llm import LlmChatRequest, LlmChatResult, LlmConnection
from app.domain.models.dictionary import DictionaryVersion
from app.domain.models.dictionary_sync import DictionarySource, DictionarySyncRun
from app.domain.vocabulary import VocabularyList
from app.infrastructure.repositories.dictionary_repository import (
    DictionaryRepository,
    NewDictionaryVersion,
)
from app.infrastructure.repositories.dictionary_sync_repository import (
    DictionarySyncRepository,
)
from app.infrastructure.repositories.vocabulary_repository import VocabularyRepository
from app.services.analysis.dictionary_workbook import load_dictionary, records_digest
from app.services.dictionary_curation.decisions import Decisions
from app.services.dictionary_curation.decisions import load as load_decisions
from app.services.dictionary_curation.judge import JudgeOutcome, judge_rows, sample_rows
from app.services.dictionary_curation.normalize import normalize_tables
from app.services.dictionary_curation.scope import GATE, REASON_CODE, Scope, plan_scope
from app.services.dictionary_curation.score import score_card
from app.services.dictionary_reading import dictionary_identity
from app.services.dictionary_service import write_dictionary_version
from app.services.dictionary_sync_describe import describe_tables
from app.services.dictionary_sync_fill import (
    CHUNK_COLUMNS,
    PARALLEL_CALLS,
    column_wanted,
    count_empty,
    fill_tables,
    suggest,
    table_wanted,
)
from app.services.dictionary_sync_merge import (
    ORIGIN_ADMIN,
    Change,
    MergePlan,
    fold,
    merge,
)
from app.services.llm_connections import LlmGateway
from app.services.search_index import (
    ChangePlan,
    IndexTrigger,
    SearchIndex,
    ServingEngine,
)
from app.services.search_inputs import SearchInputs

logger = logging.getLogger("app.dictionary")

REMOVAL_LIMIT = 0.10
DEFAULT_CALL_MS = 30_000  # a dictionary call's duration before any was logged
MAX_STORED_WARNINGS = 200
KIND_UPDATE = "guncelleme"
KIND_ROLLBACK = "geri_donus"

RUN_IN_PROGRESS_MESSAGE = "Bir sözlük güncellemesi sürüyor; bitince yeniden deneyin."
SOURCE_NOT_CONFIGURED_MESSAGE = "Önce kaynak bağlantısını ve parolasını kaydedin."
SOURCE_UNAVAILABLE_MESSAGE = "Sözlük kaynağına ulaşılamadı."
SOURCE_INVALID_MESSAGE = (
    "Sözlük kaynağının yapısı beklenenden farklı veya sınırları aşıyor."
)
SOURCE_EMPTY_MESSAGE = "Sözlük kaynağı boş döndü; etkin sözlük değişmedi."
INTERRUPTED_MESSAGE = "Güncelleme uygulama yeniden başladığı için kesildi."
FAILED_MESSAGE = "Güncelleme beklenmedik bir hatayla durdu; etkin sözlük değişmedi."


def run_in_progress() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT, "dictionary_sync_in_progress", RUN_IN_PROGRESS_MESSAGE
    )


def source_not_configured() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "dictionary_source_not_configured",
        SOURCE_NOT_CONFIGURED_MESSAGE,
    )


def target_message(databases: tuple[str, ...]) -> str:
    return "Şu veritabanları okunamadı, etkin sözlük değişmedi: " + ", ".join(databases)


def source_context(tenant_public_id: str, row: DictionarySource) -> str:
    """A saved password opens only for the address it was saved with."""

    return f"dictionary_source:{tenant_public_id}:{row.public_id}:{row.host}:{row.port}"


class SourceKeys:
    def __init__(self, settings: Settings) -> None:
        key = settings.settings_encryption_key
        self._cipher = (
            SecretCipher(decode_encryption_key(key.get_secret_value()))
            if key is not None
            else None
        )

    @property
    def available(self) -> bool:
        return self._cipher is not None

    def seal(
        self, password: str, *, tenant_public_id: str, row: DictionarySource
    ) -> str:
        assert self._cipher is not None
        return self._cipher.encrypt(
            password, context=source_context(tenant_public_id, row)
        )

    def open(self, row: DictionarySource, *, tenant_public_id: str) -> str | None:
        if self._cipher is None or row.password_ciphertext is None:
            return None
        try:
            return self._cipher.decrypt(
                row.password_ciphertext, context=source_context(tenant_public_id, row)
            )
        except SecretUnreadable:
            return None


def connection_of(row: DictionarySource, password: str) -> SourceConnection:
    return SourceConnection(
        host=row.host,
        port=row.port,
        database=row.database_name,
        username=row.username,
        password=password,
        encrypt=row.encrypt,
    )


def counts_of(plan: MergePlan) -> dict[str, int]:
    kinds: dict[str, int] = {}
    seen: set[tuple[str, str, str]] = set()
    for change in plan.changes:
        key = (change.kind, change.table_key, change.column_name)
        if key not in seen:
            seen.add(key)
            kinds[change.kind] = kinds.get(change.kind, 0) + 1
    new_columns = sum(len(t.columns) for t in plan.tables if t.is_new)
    return {
        "tables_added": kinds.get("table_added", 0),
        "tables_removed": plan.removed_tables,
        "tables_changed": kinds.get("table_changed", 0),
        "tables_excluded": kinds.get("table_excluded", 0),
        "tables_corrected": kinds.get("table_corrected", 0),
        "columns_added": kinds.get("column_added", 0) + new_columns,
        "columns_removed": plan.removed_columns,
        "columns_changed": kinds.get("column_changed", 0),
        "columns_excluded": kinds.get("column_excluded", 0),
        "columns_corrected": kinds.get("column_corrected", 0),
    }


def with_extra_headers(records: list[dict[str, str]], headers: list[str]) -> None:
    """Every record carries the version's extra columns, as the stored read gives them back."""

    for record in records:
        for header in headers:
            record.setdefault(header, "")


def kept_digests(scope: Scope, answered: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """The digests to store: a row whose computation changed but which the model did not answer
    keeps its old digest (and its object its old gate), so the next update looks at it again."""

    held = {row for row, reason in scope.columns.items() if reason == REASON_CODE and row not in answered}
    objects = {table for table, _ in held}
    return {
        key: value
        for key, value in scope.digests.items()
        if key not in held and not (key[1] == GATE and key[0] in objects)
    }


async def remember(
    session: AsyncSession, tenant_id: int, digests: dict[tuple[str, str], str], plan: MergePlan | None
) -> None:
    """Store the trail digests for the next update; without a plan, nothing is dropped."""

    repository = DictionarySyncRepository(session)
    await repository.save_trail_digests(tenant_id, digests, datetime.now(UTC))
    if plan is not None:
        await repository.drop_trail_digests(
            tenant_id,
            [(fold(t.key), fold(c.record["ColumnName"])) for t in plan.tables for c in t.columns]
            + [(fold(t.key), GATE) for t in plan.tables],
        )


def described_again(plan: MergePlan, scope: Scope) -> tuple[set[tuple[str, str]], set[str]]:
    """The rows and objects to describe again: a changed computation, or a text the source rewrote."""

    rows = set(scope.columns)
    rows.update(
        (fold(c.table_key), fold(c.column_name))
        for c in plan.changes
        if c.kind == "column_changed" and c.field == "ColumnDescription" and c.origin == "kaynak"
    )
    objects = {
        fold(c.table_key)
        for c in plan.changes
        if c.kind == "table_changed" and c.field == "ObjectDescription" and c.origin == "kaynak"
    }
    return rows, objects


@dataclass(frozen=True, slots=True)
class Started:
    run_id: int
    public_id: str


class _RunFailed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


class DictionarySync:
    def __init__(
        self,
        *,
        index: SearchIndex,
        models: LlmGateway,
        source: DictionarySourcePort,
        keys: Callable[[], SourceKeys],
        session_factory: async_sessionmaker[AsyncSession],
        kept_databases: Sequence[str] = (),
        decisions: Decisions | None = None,
        requires_approval: bool = False,
        judge_sample: int = 40,
        chat_model: str = "",
        reasoning_effort: str | None = None,
        judge_reasoning_effort: str | None = None,
    ) -> None:
        self.kept_databases = tuple(kept_databases)
        self.decisions = decisions or load_decisions()
        # Every update with changes waits for an admin's approval, the score card beside it.
        self.requires_approval = requires_approval
        self.judge_sample = judge_sample
        # The dictionary's own model and reasoning (empty / None: the integration's own).
        self.chat_model = chat_model
        self.reasoning_effort = reasoning_effort
        self.judge_reasoning_effort = judge_reasoning_effort
        self.index = index
        self.models = models
        self.source = source
        self.keys = keys
        self.session_factory = session_factory
        self._tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ lifecycle

    async def run_startup(self, database_ready: Callable[[], Any]) -> None:
        while not await database_ready():
            await asyncio.sleep(1.0)
        try:
            now = datetime.now(UTC)
            async with self.session_factory() as session, session.begin():
                await DictionarySyncRepository(session).interrupt_running(
                    {
                        "status": "interrupted",
                        "phase": "done",
                        "finished_at": now,
                        "error_code": "interrupted",
                        "error_message": INTERRUPTED_MESSAGE,
                    }
                )
                await self._prune(session, await self.index.tenant_id(), now)
        except Exception as error:  # noqa: BLE001 - logged; the next start tries again
            log_event(
                logger,
                "dictionary.sync_startup_failed",
                error_type=type(error).__name__,
            )

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @staticmethod
    async def _prune(session: AsyncSession, tenant_id: int, now: datetime) -> None:
        before = now - timedelta(days=VERSION_RETENTION_DAYS)
        pruned = await DictionaryRepository(session).prune_expired(
            tenant_id, before=before, now=now
        )
        if pruned:
            log_event(logger, "dictionary.pruned_expired", versions=pruned)

    # ------------------------------------------------------------------ start

    async def _open_run(
        self, tenant_id: int, kind: str, user_id: int, phase: str
    ) -> Started:
        now = datetime.now(UTC)
        try:
            async with self.session_factory() as session, session.begin():
                run = DictionarySyncRun(
                    tenant_id=tenant_id,
                    kind=kind,
                    status="running",
                    phase=phase,
                    started_at=now,
                    created_at=now,
                    updated_at=now,
                    created_by=user_id,
                    updated_by=user_id,
                )
                session.add(run)
                await session.flush()
                return Started(run.dictionary_sync_run_id, run.public_id)
        except IntegrityError:
            raise run_in_progress() from None

    def _spawn(self, work: Any) -> None:
        task = asyncio.create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start_update(
        self, tenant_id: int, tenant_public_id: str, user_id: int
    ) -> str:
        async with self.session_factory() as session:
            await self._connection(session, tenant_id, tenant_public_id)
        started = await self._open_run(tenant_id, KIND_UPDATE, user_id, "reading")
        self._spawn(
            self._guarded(
                started.run_id,
                self._update(started.run_id, tenant_id, tenant_public_id, user_id),
            )
        )
        return started.public_id

    async def start_restore(self, tenant_id: int, version_id: int, user_id: int) -> str:
        started = await self._open_run(tenant_id, KIND_ROLLBACK, user_id, "indexing")
        self._spawn(
            self._guarded(
                started.run_id,
                self._restore(started.run_id, tenant_id, version_id, user_id),
            )
        )
        return started.public_id

    async def _connection(
        self, session: AsyncSession, tenant_id: int, tenant_public_id: str
    ) -> SourceConnection:
        row = await DictionarySyncRepository(session).source(tenant_id)
        password = row and self.keys().open(row, tenant_public_id=tenant_public_id)
        if row is None or not password:
            raise source_not_configured()
        return connection_of(row, password)

    # ------------------------------------------------------------------ run plumbing

    async def _guarded(self, run_id: int, work: Any) -> None:
        try:
            await work
        except asyncio.CancelledError:
            await self._end(run_id, "interrupted", "interrupted", INTERRUPTED_MESSAGE)
            raise
        except _RunFailed as failed:
            await self._end(run_id, "failed", failed.code, failed.message)
        except Exception as error:  # noqa: BLE001 - the run ends failed; the type is logged
            log_event(logger, "dictionary.sync_failed", error_type=type(error).__name__)
            await self._end(run_id, "failed", "dictionary_sync_failed", FAILED_MESSAGE)

    async def _end(self, run_id: int, state: str, code: str, message: str) -> None:
        await self._set(
            run_id,
            status=state,
            phase="done",
            finished_at=datetime.now(UTC),
            error_code=code,
            error_message=message,
        )
        log_event(logger, "dictionary.sync_end", outcome=state, error_code=code)

    async def _set(self, run_id: int, **values: Any) -> None:
        async with self.session_factory() as session, session.begin():
            run = await DictionarySyncRepository(session).run_by_id(run_id)
            for name, value in values.items():
                setattr(run, name, value)

    async def _record(
        self,
        session: AsyncSession,
        run_id: int,
        changes: list[Change],
        suggestions: list[Any],
        **values: Any,
    ) -> None:
        repository = DictionarySyncRepository(session)
        await repository.add_changes(run_id, changes)
        await repository.add_suggestions(run_id, suggestions)
        run = await repository.run_by_id(run_id)
        for name, value in values.items():
            setattr(run, name, value)

    # ------------------------------------------------------------------ update

    async def _read(self, connection: SourceConnection) -> Any:
        try:
            snapshot = await self.source.read(connection)
        except SourceUnavailable:
            raise _RunFailed(
                "dictionary_source_unavailable", SOURCE_UNAVAILABLE_MESSAGE
            ) from None
        except SourceInvalid:
            raise _RunFailed(
                "dictionary_source_invalid", SOURCE_INVALID_MESSAGE
            ) from None
        except TargetUnavailable as target:
            raise _RunFailed(
                "dictionary_target_unavailable", target_message(tuple(target.databases))
            ) from None
        if not snapshot.tables or not snapshot.columns:
            raise _RunFailed("dictionary_source_invalid", SOURCE_EMPTY_MESSAGE)
        return snapshot

    async def _reject_waiting(self, tenant_id: int, user_id: int) -> None:
        """A new update replaces a version that was still waiting for approval."""

        now = datetime.now(UTC)
        async with self.session_factory() as session, session.begin():
            repository = DictionaryRepository(session)
            for run in await DictionarySyncRepository(session).pending_runs(tenant_id):
                waiting = await repository.version(tenant_id, DictionaryStatus.PENDING)
                if waiting is not None:
                    await repository.prune(waiting, user_id=user_id, now=now)
                run.status = "rejected"
                run.finished_at = now

    def connection_for(self, target: LlmConnection, effort: str | None) -> LlmConnection:
        """The integration's connection with the dictionary's own model and reasoning."""

        return replace(
            target,
            chat_model=self.chat_model or target.chat_model,
            reasoning_effort=target.reasoning_effort if effort is None else effort,
        )

    async def preview(self, tenant_id: int, tenant_public_id: str) -> dict[str, Any]:
        """What an update would look at and how long its model work would take; writes nothing.

        Reads the source as an update does, plans the scope against the stored digests and counts
        the model calls: fill chunks of tables with empty fields, descriptions of rows and objects
        in scope, the verifier's sample and the suggestion call. The duration uses the average of
        recent dictionary calls (analysis calls before the first update), two calls at a time.
        """

        async with self.session_factory() as session:
            connection = await self._connection(session, tenant_id, tenant_public_id)
        snapshot = await self._read(connection)
        async with self.session_factory() as session:
            repository = DictionaryRepository(session)
            active = await repository.version(tenant_id, DictionaryStatus.ACTIVE)
            objects = await repository.objects(active) if active else []
            columns = await repository.columns(active) if active else []
            object_meta = await repository.object_meta(active) if active else []
            column_meta = await repository.column_meta(active) if active else []
            stored = await DictionarySyncRepository(session).trail_digests(tenant_id)
            average_ms = await DictionarySyncRepository(session).average_call_ms(tenant_id)
        plan = merge(snapshot, objects, object_meta, columns, column_meta, self.kept_databases)
        scope = await asyncio.to_thread(plan_scope, plan.tables, snapshot.code, stored)
        again_rows, again_objects = described_again(plan, scope)
        fill = 0
        for table in plan.tables:
            if not table.needs_model:
                continue
            empty = sum(1 for c in table.columns if column_wanted(c))
            fill += max(1 if table_wanted(table) else 0, -(-empty // CHUNK_COLUMNS))
        describe_rows = {
            (fold(t.key), fold(c.record["ColumnName"]))
            for t in plan.tables
            for c in t.columns
            if (c.is_new or (fold(t.key), fold(c.record["ColumnName"])) in again_rows)
            and c.origins.get("ColumnDescription") != ORIGIN_ADMIN
        }
        describe_objects = {fold(t.key) for t in plan.tables if t.is_new} | again_objects
        needs_model = any(t.needs_model for t in plan.tables) or bool(describe_rows)
        judge = min(self.judge_sample, len(describe_rows)) if self.judge_sample else 0
        calls = fill + len(describe_rows) + len(describe_objects) + judge + (1 if needs_model else 0)
        seconds = round(calls * (average_ms or DEFAULT_CALL_MS) / 1000 / PARALLEL_CALLS)
        return {
            "has_changes": plan.has_changes,
            "scope": scope.counts(),
            "tables_needing_model": sum(1 for t in plan.tables if t.needs_model),
            "rows_to_describe": len(describe_rows),
            "objects_to_describe": len(describe_objects),
            "model_calls": calls,
            "average_call_seconds": round((average_ms or DEFAULT_CALL_MS) / 1000, 1),
            "estimated_seconds": seconds,
            "requires_approval": self.requires_approval,
        }

    async def _update(
        self, run_id: int, tenant_id: int, tenant_public_id: str, user_id: int
    ) -> None:
        await self._reject_waiting(tenant_id, user_id)
        async with self.session_factory() as session:
            connection = await self._connection(session, tenant_id, tenant_public_id)
        snapshot = await self._read(connection)
        await self._set(run_id, phase="comparing")

        async with self.session_factory() as session:
            repository = DictionaryRepository(session)
            active = await repository.version(tenant_id, DictionaryStatus.ACTIVE)
            objects = await repository.objects(active) if active else []
            columns = await repository.columns(active) if active else []
            object_meta = await repository.object_meta(active) if active else []
            column_meta = await repository.column_meta(active) if active else []
            terms = await VocabularyRepository(session).items(
                tenant_id, VocabularyList.TERMS
            )
            stopwords = await VocabularyRepository(session).items(
                tenant_id, VocabularyList.STOPWORDS
            )
            stored_digests = await DictionarySyncRepository(session).trail_digests(tenant_id)
        plan = merge(
            snapshot, objects, object_meta, columns, column_meta, self.kept_databases
        )
        # Only what changed is looked at: new rows, a changed source text, a changed computation.
        scope = await asyncio.to_thread(plan_scope, plan.tables, snapshot.code, stored_digests)
        previous = active.version if active else ""
        object_headers = list(active.object_extra_headers) if active else []
        column_headers = list(active.column_extra_headers) if active else []
        warnings: list[str] = []
        if self.kept_databases:
            names = ", ".join(self.kept_databases)
            warnings.append(f"{names} değerlendirilmedi; mevcut kayıtları korundu.")
        if snapshot.skipped:
            warnings.append(
                f"{snapshot.skipped} kaynak satırı bozuk veya yinelenen olduğu için atlandı."
            )

        again_rows, again_objects = described_again(plan, scope)
        scoped = {key for key, _ in again_rows} | again_objects
        # The rows the model will describe get their code trail (a changed source text too).
        await asyncio.to_thread(scope.ensure_evidence, plan.tables, again_rows)
        work = [t for t in plan.tables if t.needs_model or fold(t.key) in scoped]
        changed = list(work)
        filled = calls = failures = 0
        suggestions: list[Any] = []
        model = ""
        described_rows: set[tuple[str, str]] = set()
        evidence: dict[Any, Any] = dict(scope.evidence)
        chat_with: Any = None
        if work:
            await self._set(
                run_id, phase="filling", progress_total=len(work), progress_done=0
            )
            target = await self.models.snapshot(
                tenant_id=tenant_id, tenant_public_id=tenant_public_id
            )
            if isinstance(target, LlmConnection):
                describer = self.connection_for(target, self.reasoning_effort)
                verifier = self.connection_for(target, self.judge_reasoning_effort)
                model = describer.chat_model

                async def chat(request: LlmChatRequest) -> LlmChatResult:
                    return await self.models.port.chat(describer, request)

                async def verify(request: LlmChatRequest) -> LlmChatResult:
                    return await self.models.port.chat(verifier, request)

                chat_with = verify

                async def progress(done: int, total: int) -> None:
                    await self._set(run_id, progress_done=done, progress_total=total)

                outcome = await fill_tables(plan.tables, chat, progress)
                plan.changes.extend(outcome.changes)
                warnings.extend(outcome.warnings)
                described = await describe_tables(
                    plan.tables, chat, evidence, rows=again_rows, objects=again_objects
                )
                plan.changes.extend(described.changes)
                warnings.extend(described.warnings)
                described_rows = described.answered
                filled = outcome.filled + described.changed
                calls = outcome.calls + described.calls
                failures = outcome.failures + described.failures
                known = {fold(i["term"]) for i in terms} | {
                    fold(i["word"]) for i in stopwords
                }
                for item in terms:
                    known.update(fold(e) for e in item["equivalents"])
                suggestions, answered = await suggest(changed, known, chat)
                if not answered:
                    warnings.append("Model terim ve durak kelime önerisi üretemedi.")
            else:
                warnings.append(
                    "Model bağlantısı kullanılamadı; boş alanlar sonraki güncellemede doldurulacak."
                )

        # The owner's rules on every text, model-written or not; an admin's edit is left alone.
        normalized = await asyncio.to_thread(
            normalize_tables, plan.tables, snapshot.code, self.decisions, evidence
        )
        plan.changes.extend(normalized.changes)

        # The verifier: a second prompt scores a sample of the texts this run wrote.
        model_rows = {
            (fold(c.table_key), fold(c.column_name))
            for c in plan.changes
            if c.kind == "column_changed"
            and c.column_name
            and c.field == "ColumnDescription"
            and c.origin in ("model", "duzenleme")
        }
        digests = kept_digests(scope, described_rows)
        judged: JudgeOutcome | None = None
        if chat_with is not None and model_rows and self.judge_sample:
            chosen = sample_rows(plan.tables, sorted(model_rows), self.judge_sample, seed=str(run_id))
            judged = await judge_rows(chosen, chat_with, evidence, len(model_rows))
        score = score_card(
            plan.tables,
            self.decisions,
            judged,
            model_calls=calls + (judged.calls if judged else 0),
            model_failures=failures + (judged.failures if judged else 0),
            normalized=len(normalized.changes),
            scope={**scope.counts(), "written_rows": len(model_rows)},
        )

        counts = {
            **counts_of(plan),
            "fields_filled": filled,
            "fields_normalized": len(normalized.changes),
            **scope.counts(),
            "fields_empty": count_empty(plan.tables),
            "model_calls": calls,
            "model_failures": failures,
            "warnings": len(warnings),
        }
        report: dict[str, Any] = {
            "score": score,
            "counts": counts,
            "warnings": warnings[:MAX_STORED_WARNINGS],
            "previous_version": previous,
            "model": model,
        }
        if not plan.has_changes:
            async with self.session_factory() as session, session.begin():
                await remember(session, tenant_id, digests, plan)
                await self._record(
                    session,
                    run_id,
                    plan.changes,
                    suggestions,
                    status="no_change",
                    phase="done",
                    finished_at=datetime.now(UTC),
                    new_version=previous,
                    **report,
                )
            return

        records = plan.objects()
        rows = plan.columns()
        with_extra_headers(records, object_headers)
        with_extra_headers(rows, column_headers)
        digest = records_digest(records, rows)
        number = f"{digest}-{len(rows)}"
        now = datetime.now(UTC)
        version = NewDictionaryVersion(
            version=number,
            content_digest=digest,
            source_name=connection.database,
            channel=ImportChannel.SOURCE.value,
            imported_at=now,
            row_count=len(rows),
            column_count=len(rows),
            object_count=len(records),
            warnings=warnings[:MAX_KEPT_WARNINGS],
            warning_count=len(warnings),
            objects=records,
            columns=rows,
            object_extra_headers=object_headers,
            column_extra_headers=column_headers,
            object_meta=plan.object_meta(),
            column_meta=plan.column_meta(),
        )

        if active is not None and (
            self.requires_approval or plan.removal_share() > REMOVAL_LIMIT
        ):
            async with self.session_factory() as session, session.begin():
                written, _pruned = await DictionaryRepository(session).write_version(
                    tenant_id,
                    version,
                    user_id=user_id,
                    now=now,
                    status=DictionaryStatus.PENDING,
                )
                # The digests wait with the version: they are stored when it is approved.
                report["pending_digests"] = [[t, c, d] for (t, c), d in sorted(digests.items())]
                await self._record(
                    session,
                    run_id,
                    plan.changes,
                    suggestions,
                    status="pending_approval",
                    phase="done",
                    finished_at=now,
                    new_version=number,
                    dictionary_version_id=written.dictionary_version_id,
                    **report,
                )
            log_event(
                logger, "dictionary.sync_end", outcome="pending_approval", error_code=""
            )
            return

        await self._set(run_id, phase="indexing")

        async def write(session: AsyncSession) -> None:
            written = await write_dictionary_version(
                session, tenant_id, version, user_id=user_id, now=now
            )
            await self._prune(session, tenant_id, now)
            await remember(session, tenant_id, digests, plan)
            await self._record(
                session,
                run_id,
                plan.changes,
                suggestions,
                status="completed",
                phase="done",
                finished_at=datetime.now(UTC),
                new_version=number,
                dictionary_version_id=written.dictionary_version_id,
                **report,
            )

        await self.swap(records, rows, number, digest, write)
        log_event(
            logger,
            "dictionary.sync_end",
            outcome="completed",
            error_code="",
            object_count=len(records),
            column_count=len(rows),
            model_calls=calls,
            model_failures=failures,
        )

    async def swap(
        self,
        objects: list[dict[str, str]],
        columns: list[dict[str, str]],
        number: str,
        digest: str,
        write: Any,
    ) -> None:
        """Build the new engine first; the write commits only when the build succeeded."""

        async def plan(
            inputs: SearchInputs, _serving: ServingEngine | None
        ) -> ChangePlan:
            dictionary = load_dictionary(objects, columns, number, digest)
            return ChangePlan(
                inputs=inputs.replace(
                    dictionary=dictionary,
                    dictionary_identity=dictionary_identity(number, digest),
                ),
                write=write,
            )

        await self.index.change(IndexTrigger.DICTIONARY, plan)

    # ------------------------------------------------------------------ rollback

    async def _restore(
        self, run_id: int, tenant_id: int, version_id: int, user_id: int
    ) -> None:
        async with self.session_factory() as session:
            repository = DictionaryRepository(session)
            active = await repository.version(tenant_id, DictionaryStatus.ACTIVE)
            target = await session.get(DictionaryVersion, version_id)
            assert target is not None
            objects = await repository.objects(target)
            columns = await repository.columns(target)
            object_meta = await repository.object_meta(target)
            column_meta = await repository.column_meta(target)
        previous = active.version if active else ""
        if active is not None and active.content_digest == target.content_digest:
            await self._set(
                run_id,
                status="no_change",
                phase="done",
                finished_at=datetime.now(UTC),
                previous_version=previous,
                new_version=previous,
            )
            return
        now = datetime.now(UTC)
        version = NewDictionaryVersion(
            version=target.version,
            content_digest=target.content_digest,
            source_name=target.source_name,
            channel=ImportChannel.ROLLBACK.value,
            imported_at=now,
            row_count=target.row_count,
            column_count=target.column_count,
            object_count=target.object_count,
            warnings=list(target.warnings),
            warning_count=target.warning_count,
            objects=objects,
            columns=columns,
            object_extra_headers=list(target.object_extra_headers),
            column_extra_headers=list(target.column_extra_headers),
            object_meta=object_meta,
            column_meta=column_meta,
        )

        async def write(session: AsyncSession) -> None:
            written = await write_dictionary_version(
                session, tenant_id, version, user_id=user_id, now=now
            )
            await self._prune(session, tenant_id, now)
            await self._record(
                session,
                run_id,
                [],
                [],
                status="completed",
                phase="done",
                finished_at=datetime.now(UTC),
                previous_version=previous,
                new_version=target.version,
                dictionary_version_id=written.dictionary_version_id,
            )

        await self.swap(objects, columns, target.version, target.content_digest, write)
