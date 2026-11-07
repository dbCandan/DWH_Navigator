"""The term list's run over PostgreSQL with a stand-in for the analysis jobs
(data-dictionary 005-list-search Requirement 4-10, 18, 19; Acceptance 3).

The stand-in hands out real job objects whose end each test decides, so the order, the one term
at a time, the writes after every term, the stop, the resume (the source's
``test_term_list_resumes_after_stop`` included), the kept "Analiz yapılamadı" answers, the
retried errors, the safe error message, the time without the pause and every way a list is
interrupted are checked exactly.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from openpyxl import Workbook

from app.core.errors import ApplicationError
from app.db.session import async_session_factory
from app.domain.analysis import AnalysisResult
from app.domain.analysis_records import Flow, JobState, Origin
from app.domain.term_lists import TERM_ERROR_MESSAGE
from app.services.analysis import serialize, trace
from app.services.analysis.jobs import AnalysisJob, Asker, ListTerm, Tenant
from app.services.term_lists import TermLists
from tests.integration.conftest import SignedIn
from tests.integration.data_dictionary import DataDictionary, sql
from tests.parity.fake_model import NO_MODEL, NORMAL, FakeAnalyst
from tests.parity.harness import STOPWORDS, TERMS, WORKBOOK
from tests.parity.run_target import TargetSide

pytestmark = pytest.mark.integration


def xlsx(cells: list[Any]) -> bytes:
    book = Workbook()
    ws = book.active
    assert ws is not None
    for value in cells:
        ws.append([value])
    out = BytesIO()
    book.save(out)
    return out.getvalue()


@pytest.fixture(scope="module")
def answers() -> dict[str, AnalysisResult]:
    """Real answers of the in-process engine: an analyst answer and a "yapılamadı" one."""

    side = TargetSide()
    dictionary, _ = side.parse_dictionary(WORKBOOK.read_bytes())
    groups, stop = side.word_lists(TERMS, STOPWORDS)
    core = FakeAnalyst()
    engine = side.engine(dictionary, {}, groups, stop, side.client(core))
    out = {}
    for name, scenario in (("analyst", NORMAL), ("unavailable", NO_MODEL)):
        core.begin("kart limit doluluk", scenario)
        out[name] = engine.analyze("kart limit doluluk", 5)
    assert out["analyst"].analyst and not out["unavailable"].analyst
    return out


@dataclass
class FakeJobs:
    """The jobs' side a list uses; ``plan`` says how a term ends (default: an analyst answer)."""

    answers: dict[str, AnalysisResult]
    accepting: bool = True
    plan: dict[str, str] = field(default_factory=dict)  # term -> hold, fail, raise, unavailable
    gates: dict[str, asyncio.Event] = field(default_factory=dict)
    started: list[AnalysisJob] = field(default_factory=list)
    active: int = 0
    most_active: int = 0
    index: Any = field(
        default_factory=lambda: SimpleNamespace(
            engine=lambda: SimpleNamespace(dictionary=SimpleNamespace(version="abc123-1557"))
        )
    )

    def ready(self) -> None:
        if not self.accepting:
            raise ApplicationError(503, "analysis_unavailable", "kapanıyor")

    def asked(self) -> list[str]:
        return [job.query for job in self.started]

    async def start(
        self,
        *,
        tenant: Tenant,
        asker: Asker,
        query: str,
        top: int,
        fresh: bool,
        origin: Origin = Origin.QUESTION,
        list_term: ListTerm | None = None,
    ) -> AnalysisJob:
        self.ready()
        if self.plan.get(query) == "raise":
            raise RuntimeError("gizli /sunucu/yolu ve model adresi")
        job = AnalysisJob(
            public_id=f"job-{len(self.started) + 1}",
            tenant=tenant,
            asker=asker,
            origin=origin,
            list_term=list_term,
            query=query,
            top=top,
            fresh=fresh,
            accepted_at=datetime.now(UTC),
            accepted_perf=time.perf_counter(),
            timeline=trace.Trace(),
            text_key=query,
        )
        self.started.append(job)
        asyncio.get_running_loop().create_task(self._run(job))
        return job

    async def _run(self, job: AnalysisJob) -> None:
        self.active += 1
        self.most_active = max(self.most_active, self.active)
        try:
            job.state = JobState.RUNNING
            kind = self.plan.get(job.query, "")
            if kind == "hold":
                gate = self.gates.setdefault(job.query, asyncio.Event())
                await gate.wait()
            else:
                await asyncio.sleep(0.01)
            if job.terminal:
                return
            if kind == "fail":
                job.state, job.flow = JobState.FAILED, Flow.FAILED
            elif kind == "unavailable":
                job.state, job.flow = JobState.COMPLETED, Flow.UNAVAILABLE
                job.result = self.answers["unavailable"]
            else:
                job.state, job.flow = JobState.COMPLETED, Flow.ANALYST
                job.result = self.answers["analyst"]
        finally:
            self.active -= 1
            job.done.set()

    def view_of(self, job: AnalysisJob) -> Any:
        return job

    async def cancel(self, view: Any) -> Any:
        job: AnalysisJob = view
        if not job.terminal:
            job.state, job.flow = JobState.CANCELLED, Flow.CANCELLED
            job.done.set()
        return job

    async def present(
        self, tenant_id: int, user_public_id: str, result: AnalysisResult, analysis_id: str | None
    ) -> dict[str, Any]:
        return serialize.analysis(result)

    def shutdown(self) -> None:
        self.accepting = False
        for job in self.started:
            if not job.terminal:
                job.state, job.flow = JobState.INTERRUPTED, Flow.INTERRUPTED
                job.done.set()

    def release(self, term: str) -> None:
        self.gates.setdefault(term, asyncio.Event()).set()


@dataclass
class Clock:
    now: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class Bench:
    lists: TermLists
    jobs: FakeJobs
    clock: Clock
    tenant: Tenant
    owner: Asker
    user: SignedIn

    async def start(self, *terms: str) -> dict[str, Any]:
        return await self.lists.start(
            tenant=self.tenant, owner=self.owner, file_name="t.xlsx", data=xlsx(["Terim", *terms])
        )

    async def snapshot(self, list_id: str) -> dict[str, Any]:
        return await self.lists.snapshot(self.tenant.tenant_id, self.owner.public_id, list_id)

    async def until(self, list_id: str, status: str, timeout: float = 10.0) -> dict[str, Any]:
        async with asyncio.timeout(timeout):
            while True:
                snap = await self.snapshot(list_id)
                if snap["status"] == status:
                    return snap
                await asyncio.sleep(0.02)

    async def until_asked(self, count: int, timeout: float = 10.0) -> None:
        async with asyncio.timeout(timeout):
            while len(self.jobs.started) < count:
                await asyncio.sleep(0.01)


@pytest.fixture
async def bench(dd: DataDictionary, answers: dict[str, AnalysisResult]) -> AsyncIterator[Bench]:
    await sql("DELETE FROM term_list")
    user = await dd.auth.account(dd.admin, "kullanici")
    rows = await sql(
        "SELECT u.user_id, u.display_name, t.tenant_id, t.public_id FROM app_user u "
        "JOIN tenant t ON t.tenant_id = u.home_tenant_id WHERE u.public_id = :p",
        p=user.public_id,
    )
    user_id, display_name, tenant_id, tenant_public_id = rows[0]
    jobs = FakeJobs(answers)
    clock = Clock()
    lists = TermLists(jobs=jobs, session_factory=async_session_factory, clock=clock)
    try:
        yield Bench(
            lists,
            jobs,
            clock,
            Tenant(tenant_id, tenant_public_id),
            Asker(user_id, user.public_id, display_name),
            user,
        )
    finally:
        for gate in jobs.gates.values():
            gate.set()
        lists.closing = True
        jobs.shutdown()
        await lists.shutdown()


async def items(list_id: str) -> list[tuple[Any, ...]]:
    rows = await sql(
        "SELECT i.position, i.answer IS NOT NULL, i.flow, i.error_code, i.error_message "
        "FROM term_list_item i JOIN term_list l ON l.term_list_id = i.term_list_id "
        "WHERE l.public_id = :p ORDER BY i.position",
        p=list_id,
    )
    return [tuple(r) for r in rows]


async def test_terms_go_one_at_a_time_in_file_order_and_are_kept_at_once(bench: Bench) -> None:
    for term in ("a1", "a2", "a3"):
        bench.jobs.plan[term] = "hold"
    snap = await bench.start("a1", "a2", "a3")
    list_id = snap["id"]
    await bench.until_asked(1)
    await asyncio.sleep(0.1)
    assert bench.jobs.asked() == ["a1"]  # the next term waits for this one to end
    running = await bench.snapshot(list_id)
    assert [i["state"] for i in running["items"]] == ["running", "queued", "queued"]
    bench.jobs.release("a1")
    await bench.until_asked(2)
    assert (await items(list_id))[0][:3] == (1, True, "analyst")  # written before a2 started
    bench.jobs.release("a2")
    bench.jobs.release("a3")
    done = await bench.until(list_id, "completed")
    assert bench.jobs.asked() == ["a1", "a2", "a3"] and bench.jobs.most_active == 1
    first = bench.jobs.started[0]
    assert (first.origin, first.top, first.fresh) == (Origin.LIST, 5, False)
    assert [j.list_term for j in bench.jobs.started] == [
        ListTerm(list_id, "t.xlsx", n) for n in (1, 2, 3)
    ]
    assert done["done"] == 3 and [i["state"] for i in done["items"]] == ["answered"] * 3
    assert done["items"][0]["best"]["key"] == bench.jobs.answers["analyst"].objects[0].object_key


async def test_a_stop_cuts_the_term_and_starts_nothing_new(bench: Bench) -> None:
    bench.jobs.plan["b1"] = "hold"
    snap = await bench.start("b1", "b2", "b3")
    await bench.until_asked(1)
    started = time.monotonic()
    stopped = await bench.lists.cancel(bench.tenant.tenant_id, bench.owner.public_id, snap["id"])
    assert time.monotonic() - started < 5.0
    assert stopped["status"] == "cancelled" and stopped["stop_requested"] is True
    assert bench.jobs.started[0].state is JobState.CANCELLED
    await asyncio.sleep(0.2)
    assert bench.jobs.asked() == ["b1"]
    assert [i["state"] for i in stopped["items"]] == ["stopped"] * 3
    assert await items(snap["id"]) == [(n, False, None, None, None) for n in (1, 2, 3)]
    again = await bench.lists.cancel(bench.tenant.tenant_id, bench.owner.public_id, snap["id"])
    assert again == stopped


async def test_a_resumed_list_asks_no_answered_term_again(bench: Bench) -> None:
    """The source's test_term_list_resumes_after_stop."""
    bench.jobs.plan["müşteri yaşı"] = "hold"
    snap = await bench.start("kart limit", "müşteri yaşı", "uzay yakıtı")
    await bench.until_asked(2)
    stopped = await bench.lists.cancel(bench.tenant.tenant_id, bench.owner.public_id, snap["id"])
    assert stopped["done"] == 1
    assert [i["state"] for i in stopped["items"]] == ["answered", "stopped", "stopped"]
    bench.jobs.plan.clear()
    resumed = await bench.lists.resume(tenant=bench.tenant, owner=bench.owner, list_id=snap["id"])
    assert resumed["status"] == "running" and resumed["stop_requested"] is False
    done = await bench.until(snap["id"], "completed")
    assert done["done"] == 3 and done["stop_requested"] is False
    assert bench.jobs.asked() == ["kart limit", "müşteri yaşı", "müşteri yaşı", "uzay yakıtı"]
    with pytest.raises(ApplicationError) as nothing:
        await bench.lists.resume(tenant=bench.tenant, owner=bench.owner, list_id=snap["id"])
    assert nothing.value.code == "term_list_nothing_to_resume"


async def test_unavailable_answers_are_kept_and_failed_terms_asked_again(bench: Bench) -> None:
    bench.jobs.plan.update({"c2": "fail", "c3": "unavailable", "c4": "raise"})
    snap = await bench.start("c1", "c2", "c3", "c4", "c5")
    done = await bench.until(snap["id"], "completed")
    assert [i["state"] for i in done["items"]] == [
        "answered", "error", "answered", "error", "answered"
    ]  # fmt: skip
    assert done["items"][1]["summary"] == TERM_ERROR_MESSAGE
    assert done["items"][2]["flow"] == "unavailable"
    kept = await items(snap["id"])
    assert kept[1][3:] == ("term_analysis_failed", TERM_ERROR_MESSAGE)
    assert all("gizli" not in str(row) for row in kept)
    assert done["done"] == 5
    bench.jobs.plan = {"c3": "unavailable"}
    await bench.lists.resume(tenant=bench.tenant, owner=bench.owner, list_id=snap["id"])
    again = await bench.until(snap["id"], "completed")
    # c4 was refused by the queue itself, so the first run asked four terms
    assert bench.jobs.asked() == ["c1", "c2", "c3", "c5", "c2", "c4"]
    assert [i["state"] for i in again["items"]] == ["answered"] * 5


async def test_the_time_does_not_count_the_pause(bench: Bench) -> None:
    bench.jobs.plan["d2"] = "hold"
    snap = await bench.start("d1", "d2")
    await bench.until_asked(2)
    bench.clock.advance(10)
    running = await bench.snapshot(snap["id"])
    assert running["elapsed_ms"] == 10_000 and running["eta_ms"] is not None
    await bench.lists.cancel(bench.tenant.tenant_id, bench.owner.public_id, snap["id"])
    bench.clock.advance(100)
    stopped = await bench.snapshot(snap["id"])
    assert stopped["elapsed_ms"] == 10_000 and stopped["eta_ms"] is None
    bench.jobs.release("d2")  # the stopped job's stand-in ends; a new gate holds the next one
    bench.jobs.gates.pop("d2")
    await bench.lists.resume(tenant=bench.tenant, owner=bench.owner, list_id=snap["id"])
    await bench.until_asked(3)
    bench.clock.advance(5)
    bench.jobs.release("d2")
    done = await bench.until(snap["id"], "completed")
    assert done["elapsed_ms"] == 15_000


async def test_a_closing_process_interrupts_the_list(bench: Bench) -> None:
    bench.jobs.plan["e1"] = "hold"
    snap = await bench.start("e1", "e2")
    await bench.until_asked(1)
    bench.lists.closing = True
    bench.jobs.shutdown()
    await bench.lists.shutdown()
    after = await bench.snapshot(snap["id"])
    assert after["status"] == "interrupted" and after["done"] == 0
    assert [i["state"] for i in after["items"]] == ["stopped", "stopped"]
    assert bench.jobs.asked() == ["e1"]


async def test_a_list_left_running_is_interrupted_at_start_and_by_the_check(
    bench: Bench, answers: dict[str, AnalysisResult]
) -> None:
    bench.jobs.plan["f1"] = "hold"
    snap = await bench.start("f1")
    await bench.until_asked(1)
    assert await bench.lists.check() == 0  # it runs in this process
    later = TermLists(
        jobs=FakeJobs(answers),
        session_factory=async_session_factory,
        clock=lambda: bench.clock.now + timedelta(seconds=1),
    )
    later.started_at = bench.clock.now + timedelta(seconds=1)
    assert await later.interrupt_leftovers() == 1
    assert (await bench.snapshot(snap["id"]))["status"] == "interrupted"
    resumed_elsewhere = await sql(
        "UPDATE term_list SET status = 'running', run_started_at = now() WHERE public_id = :p "
        "RETURNING term_list_id",
        p=snap["id"],
    )
    assert resumed_elsewhere
    assert await later.check() == 1  # no run of the later process carries it
    assert (await bench.snapshot(snap["id"]))["status"] == "interrupted"


async def test_only_one_list_runs_per_owner(bench: Bench) -> None:
    """Decision 3: the same owner cannot start a second list while one runs; another owner's
    list is not an engel (data-dictionary 005-list-search Version 1.3.0)."""

    bench.jobs.plan["g1"] = "hold"
    snap = await bench.start("g1")
    with pytest.raises(ApplicationError) as running:
        await bench.start("g2")
    assert (running.value.status_code, running.value.code) == (409, "term_list_running")
    assert running.value.message == "Bir liste zaten çalışıyor; bitmesini bekleyin ya da durdurun."
    await bench.lists.cancel(bench.tenant.tenant_id, bench.owner.public_id, snap["id"])
    bench.jobs.plan["g3"] = "hold"
    other = await bench.start("g3")
    with pytest.raises(ApplicationError) as busy:
        await bench.lists.resume(tenant=bench.tenant, owner=bench.owner, list_id=snap["id"])
    assert busy.value.code == "term_list_running"
    bench.jobs.release("g3")
    await bench.until(other["id"], "completed")


async def test_two_owners_run_lists_at_the_same_time(
    bench: Bench, dd: DataDictionary
) -> None:
    """Decision 3: different owners' lists run in parallel; neither engels the other."""

    other_user = await dd.auth.account(dd.admin, "kullanici")
    rows = await sql(
        "SELECT user_id, display_name FROM app_user WHERE public_id = :p", p=other_user.public_id
    )
    other_user_id, other_display = rows[0]
    other = Asker(other_user_id, other_user.public_id, other_display)

    bench.jobs.plan["h1"] = "hold"
    bench.jobs.plan["h2"] = "hold"
    first = await bench.start("h1")
    second = await bench.lists.start(
        tenant=bench.tenant, owner=other, file_name="t.xlsx", data=xlsx(["Terim", "h2"])
    )
    await bench.until_asked(2)
    assert bench.jobs.asked() == ["h1", "h2"]
    assert bench.jobs.most_active == 2
    bench.jobs.release("h1")
    bench.jobs.release("h2")
    await bench.until(first["id"], "completed")
    async with asyncio.timeout(10):
        while True:
            snap = await bench.lists.snapshot(
                bench.tenant.tenant_id, other.public_id, second["id"]
            )
            if snap["status"] == "completed":
                break
            await asyncio.sleep(0.02)
