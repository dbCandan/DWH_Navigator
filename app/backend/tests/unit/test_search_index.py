"""The search index's life cycle with fake inputs (search-settings Requirement 9-15).

The database side is replaced by the input readers and a session whose commit is recorded; the
engine is the real one. PostgreSQL behaviour is in tests/integration.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import pytest

from app.core.errors import ApplicationError
from app.domain.analysis import Dictionary
from app.services import search_index as module
from app.services.analysis.dictionary_workbook import from_workbook, load_dictionary
from app.services.analysis.pipeline import Engine
from app.services.search_index import (
    ChangePlan,
    IndexState,
    IndexTrigger,
    SearchChangeBusy,
    SearchIndex,
    SearchIndexBuildFailed,
    SearchIndexNotReady,
    ServingEngine,
    build_engine,
)
from app.services.search_inputs import InputIdentity, SearchInputs
from app.services.search_settings_schema import defaults, settings_digest
from app.services.vocabulary_reading import stopword_forms, term_groups
from tests.unit.test_vocabulary_rules import _seed

pytestmark = pytest.mark.unit

WORKBOOK = Path(__file__).resolve().parents[1] / "fixtures" / "parity" / "sozluk_sentetik.xlsx"


def _dictionary() -> Dictionary:
    imported = from_workbook(WORKBOOK.read_bytes())
    return load_dictionary(imported.objects, imported.columns, imported.version, imported.digest)


DICTIONARY = _dictionary()


def make_inputs(**settings: Any) -> SearchInputs:
    values = {**defaults(), **settings}
    return SearchInputs(
        identity=InputIdentity(
            dictionary=f"{DICTIONARY.version}:digest",
            terms="terms-1",
            stopwords="stop-1",
            settings=settings_digest(values),
        ),
        dictionary=DICTIONARY,
        term_groups=tuple(term_groups(_seed("terms.jsonl"))),
        stopwords=stopword_forms(_seed("stopwords.jsonl")),
        settings_values=values,
    )


@dataclass
class FakeSession:
    commits: list[str]

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits.append("commit")


@dataclass
class Harness:
    index: SearchIndex
    database: dict[str, Any]
    commits: list[str] = field(default_factory=list)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Harness:
    database: dict[str, Any] = {"inputs": make_inputs(), "stored": {}}
    commits: list[str] = []

    async def read_inputs(_factory: object, _tenant: int) -> SearchInputs:
        inputs: SearchInputs = database["inputs"]
        return inputs

    async def read_identity(_factory: object, _tenant: int) -> InputIdentity:
        inputs: SearchInputs = database["inputs"]
        return inputs.identity

    class Settings:
        def __init__(self, _session: object) -> None:
            pass

        async def stored(self, _tenant: int) -> dict[str, Any]:
            stored: dict[str, Any] = database["stored"]
            return stored

    monkeypatch.setattr(module, "read_inputs", read_inputs)
    monkeypatch.setattr(module, "read_identity", read_identity)
    monkeypatch.setattr(module, "SearchSettingRepository", Settings)
    index = SearchIndex(lambda: FakeSession(commits), queue_timeout=0.3)  # type: ignore[arg-type]
    index._tenant_id = 1
    return Harness(index, database, commits)


async def _ready() -> bool:
    return True


def _fatal(calls: list[str]) -> Callable[[], None]:
    return lambda: calls.append("fatal")


async def start(harness: Harness) -> None:
    calls: list[str] = []
    await harness.index.run_startup(_ready, _fatal(calls))
    assert calls == []


def _events(caplog: pytest.LogCaptureFixture, name: str) -> list[dict[str, Any]]:
    return [
        dict(getattr(r, "structured_fields", {})) for r in caplog.records if r.getMessage() == name
    ]


def _plan(inputs: SearchInputs | None, write: Any = None, result: Any = None) -> Any:
    async def planner(_current: SearchInputs, _serving: ServingEngine | None) -> ChangePlan:
        return ChangePlan(inputs=inputs, write=write, result=result)

    return planner


# --- Requirement 10: the first build -----------------------------------------------------------


async def test_the_first_engine_is_built_once_the_database_is_ready(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.search")
    with pytest.raises(SearchIndexNotReady):
        harness.index.engine()
    assert (await harness.index.status()).state is IndexState.BUILDING
    answers = iter([False, False, True])

    async def database_ready() -> bool:
        return next(answers)

    calls: list[str] = []
    started = asyncio.get_running_loop().time()
    await harness.index.run_startup(database_ready, _fatal(calls))
    assert asyncio.get_running_loop().time() - started >= 2 * module.DATABASE_POLL_SECONDS * 0.9
    assert calls == [] and harness.index.is_serving
    status = await harness.index.status()
    assert status.state is IndexState.READY and status.trigger is IndexTrigger.STARTUP
    assert status.columns == len(DICTIONARY.columns) and status.objects == 87
    assert _events(caplog, "search_index.build")[0]["outcome"] == "ok"


async def test_a_stored_value_off_the_schema_stops_the_process(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.search")
    harness.database["stored"] = {"analyst.shortlist": 99, "removed.key": 1, "cache.enabled": 1}
    calls: list[str] = []
    await harness.index.run_startup(_ready, _fatal(calls))
    assert calls == ["fatal"] and not harness.index.is_serving
    assert _events(caplog, "search_settings.startup_invalid") == [
        {"event": "search_settings.startup_invalid", "key": "analyst.shortlist", "reason": "range"},
        {"event": "search_settings.startup_invalid", "key": "removed.key", "reason": "unknown"},
        {"event": "search_settings.startup_invalid", "key": "cache.enabled", "reason": "type"},
    ]


async def test_a_failed_first_build_stops_the_process(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.search")

    def broken(*_: Any) -> Engine:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(harness.index, "_builder", broken)
    calls: list[str] = []
    await harness.index.run_startup(_ready, _fatal(calls))
    assert calls == ["fatal"] and not harness.index.is_serving
    (event,) = _events(caplog, "search_index.build")
    assert event["outcome"] == "failed" and event["error_type"] == "RuntimeError"
    assert "secret detail" not in caplog.text


# --- Requirement 11: the change queue ----------------------------------------------------------


async def test_a_change_is_built_then_written_then_served(harness: Harness) -> None:
    await start(harness)
    old = harness.index.engine()
    new_inputs = make_inputs(**{"analyst.shortlist": 9})
    order: list[str] = []

    async def write(_session: object) -> None:
        assert harness.index.engine() is old  # still the old engine while writing
        order.append("write")

    outcome = await harness.index.change(IndexTrigger.SETTINGS, _plan(new_inputs, write, "ok"))
    assert outcome.result == "ok" and outcome.built
    assert order == ["write"] and harness.commits == ["commit"]
    assert harness.index.engine() is not old
    assert harness.index.engine().settings.analyst.shortlist == 9
    assert old.settings.analyst.shortlist == 14  # an analysis keeps the engine it started with


async def test_an_unchanged_input_builds_and_writes_nothing(harness: Harness) -> None:
    await start(harness)
    serving = harness.index.serving
    outcome = await harness.index.change(IndexTrigger.TERMS, _plan(None, None, "same"))
    assert outcome.result == "same" and not outcome.built
    assert harness.index.serving is serving and harness.commits == []


async def test_a_failed_build_writes_nothing_and_keeps_the_engine(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await start(harness)
    serving = harness.index.serving
    written: list[str] = []

    async def write(_session: object) -> None:
        written.append("write")

    def broken(*_: Any) -> Engine:
        raise ValueError("bozuk")

    monkeypatch.setattr(harness.index, "_builder", broken)
    with pytest.raises(SearchIndexBuildFailed):
        await harness.index.change(IndexTrigger.SETTINGS, _plan(make_inputs(), write))
    assert written == [] and harness.commits == []
    assert harness.index.serving is serving
    failure = (await harness.index.status()).last_failure
    assert failure is not None and failure.trigger is IndexTrigger.SETTINGS


async def test_a_failed_write_keeps_the_engine(harness: Harness) -> None:
    await start(harness)
    serving = harness.index.serving

    async def write(_session: object) -> None:
        raise OSError("database went away")

    with pytest.raises(SearchIndexBuildFailed):
        await harness.index.change(
            IndexTrigger.STOPWORDS, _plan(make_inputs(**{"analyst.shortlist": 9}), write)
        )
    assert harness.index.serving is serving and harness.commits == []
    assert harness.index.last_failure is not None


async def test_a_deliberate_refusal_passes_through(harness: Harness) -> None:
    await start(harness)
    serving = harness.index.serving

    async def write(_session: object) -> None:
        raise ApplicationError(409, "dictionary_import_in_progress", "x")

    with pytest.raises(ApplicationError) as refused:
        await harness.index.change(IndexTrigger.DICTIONARY, _plan(make_inputs(), write))
    assert refused.value.code == "dictionary_import_in_progress"
    assert harness.index.serving is serving and harness.index.last_failure is None


def _blocking_builder(release: threading.Event, entered: threading.Event) -> Any:
    def build(inputs: SearchInputs, serving: ServingEngine | None, trigger: IndexTrigger) -> Engine:
        entered.set()
        release.wait(10)
        return build_engine(inputs, serving, trigger)

    return build


async def _until(event: threading.Event) -> None:
    while not event.is_set():
        await asyncio.sleep(0.01)


async def test_a_change_waiting_too_long_is_busy_and_writes_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.search")
    await start(harness)
    release, entered = threading.Event(), threading.Event()
    monkeypatch.setattr(harness.index, "_builder", _blocking_builder(release, entered))
    first = asyncio.create_task(harness.index.change(IndexTrigger.MANUAL, _plan(make_inputs())))
    await _until(entered)
    assert (await harness.index.status()).state is IndexState.BUILDING
    written: list[str] = []

    async def write(_session: object) -> None:
        written.append("write")

    with pytest.raises(SearchChangeBusy):
        await harness.index.change(IndexTrigger.SETTINGS, _plan(make_inputs(), write))
    release.set()
    await first
    assert written == []
    assert _events(caplog, "search_change.busy") == [
        {"event": "search_change.busy", "trigger": "settings"}
    ]


async def test_two_changes_run_one_after_the_other(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await start(harness)
    release, entered = threading.Event(), threading.Event()
    monkeypatch.setattr(harness.index, "_builder", _blocking_builder(release, entered))
    harness.index._queue_timeout = 5
    order: list[str] = []

    def writer(name: str) -> Callable[[object], Awaitable[None]]:
        async def write(_session: object) -> None:
            order.append(name)

        return write

    first = asyncio.create_task(
        harness.index.change(IndexTrigger.TERMS, _plan(make_inputs(), writer("first")))
    )
    await _until(entered)
    second = asyncio.create_task(
        harness.index.change(IndexTrigger.TERMS, _plan(make_inputs(), writer("second")))
    )
    await asyncio.sleep(0.05)
    release.set()
    await asyncio.gather(first, second)
    assert order == ["first", "second"]


async def test_a_started_change_finishes_when_its_caller_goes_away(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await start(harness)
    release, entered = threading.Event(), threading.Event()
    monkeypatch.setattr(harness.index, "_builder", _blocking_builder(release, entered))
    written: list[str] = []

    async def write(_session: object) -> None:
        written.append("write")

    caller = asyncio.create_task(
        harness.index.change(
            IndexTrigger.SETTINGS, _plan(make_inputs(**{"analyst.shortlist": 7}), write)
        )
    )
    await _until(entered)
    caller.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await caller
    for _ in range(200):
        if harness.index.running is None and written:
            break
        await asyncio.sleep(0.01)
    assert written == ["write"]
    assert harness.index.engine().settings.analyst.shortlist == 7


# --- Requirement 12 and 13: no analysis lock, equal engines ----------------------------------


async def test_requests_are_served_while_an_engine_is_built(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await start(harness)

    def slow(inputs: SearchInputs, serving: ServingEngine | None, trigger: IndexTrigger) -> Engine:
        time.sleep(0.5)
        return build_engine(inputs, serving, trigger)

    monkeypatch.setattr(harness.index, "_builder", slow)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    running = asyncio.create_task(ticker())
    await harness.index.rebuild()
    running.cancel()
    assert ticks >= 20


async def test_the_reused_word_index_gives_the_engine_built_from_scratch(harness: Harness) -> None:
    await start(harness)
    first = harness.index.engine()

    async def change(trigger: IndexTrigger, **settings: Any) -> Engine:
        inputs = make_inputs(**settings)
        await harness.index.change(trigger, _plan(inputs))
        return harness.index.engine()

    immediate = await change(IndexTrigger.SETTINGS, **{"analyst.shortlist": 9})
    assert immediate.bm25 is first.bm25  # only "anında" fields changed
    reindexed = await change(
        IndexTrigger.SETTINGS, **{"analyst.shortlist": 9, "search.bm25.k1": 1.5}
    )
    assert reindexed.bm25 is not first.bm25
    manual_inputs = make_inputs(**{"analyst.shortlist": 9, "search.bm25.k1": 1.5})
    await harness.index.change(IndexTrigger.MANUAL, _plan(manual_inputs))
    assert harness.index.engine().bm25 is not reindexed.bm25

    fresh = Engine(
        DICTIONARY,
        immediate.settings,
        immediate.resources,
    )
    for query in ("kart limit doluluk oranı", "müşteri kredi kartı harcaması aylık", "x"):
        reused_rank, _ = immediate.rank_objects(query)
        fresh_rank, _ = fresh.rank_objects(query)
        assert [(m.object_key, m.score) for m in reused_rank] == [
            (m.object_key, m.score) for m in fresh_rank
        ]


async def test_stale_is_reported_once_per_difference(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.search")
    await start(harness)
    current: SearchInputs = harness.database["inputs"]
    harness.database["inputs"] = current.replace(
        terms_identity="changed elsewhere", dictionary_identity="other:x"
    )
    for _ in range(3):
        status = await harness.index.status()
        assert status.state is IndexState.STALE
        assert status.stale_inputs == ["dictionary", "terms"]
    assert _events(caplog, "search_index.stale_detected") == [
        {"event": "search_index.stale_detected", "inputs": "dictionary,terms"}
    ]
