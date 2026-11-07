"""Analysis jobs: acceptance, the queue, live progress, stopping and the end of a job
(data-dictionary 004-question-analysis Requirement 3, 8-12, 14, 18, 23, 24, Decision 2, 5-8, 15, 21).

A question is a job. Acceptance answers at once: with a saved answer the job is completed there;
otherwise it waits in one first-in first-out queue of this process. At most ``concurrency`` jobs
run at a time (4 by default), at most one per owner: different owners run in parallel and an
owner's next job waits for its running one without holding up the others (Decision 27; the source
ran one analysis at a time, "one engine, one lock"). A running job pins the serving
engine and the active chat model (llm-connection Requirement 5) and runs the engine in a worker
thread; the engine reaches the model through the job's own view of the port. Progress is a list of
content-free events kept in memory while the process lives; a stream replays it from
``Last-Event-ID``. A stop closes the open model request and ends the job as ``cancelled``; a
closing process ends queued and running jobs as ``interrupted``; a dropped stream changes nothing
(Decision 6).

Every job is an analysis record (analysis-records Decision 5): opened at acceptance, updated when
it starts and when it ends, written in one transaction each time. A record write that fails leaves
an event and the job goes on; the answer is still served from memory.

Nothing here logs or traces a question, a dictionary name, a prompt or a model reply.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import telemetry
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.rate_window import SlidingWindow
from app.domain.analysis import AnalysisResult
from app.domain.analysis_records import (
    CANCELLED_CODE,
    CANCELLED_MESSAGE,
    ERROR_MESSAGE_MAX_CHARS,
    FAILED_CODE,
    FAILED_MESSAGE,
    INTERRUPTED_CODE,
    INTERRUPTED_MESSAGE,
    MAX_TABLE_KEYS,
    REASON_MAX_CHARS,
    SUMMARY_MAX_CHARS,
    TERMINAL_STATES,
    Flow,
    JobState,
    Origin,
)
from app.domain.llm import LlmChatPort, LlmConnection, LlmOutcome, ModelState
from app.domain.models.analysis_record import AnalysisRecord
from app.domain.models.mixins import new_public_id
from app.domain.turkish_text import fold
from app.infrastructure.repositories.analysis_record_repository import (
    AnalysisRecordRepository,
    RecordRow,
)
from app.services.analysis import cancel, serialize, trace
from app.services.analysis.answer_cache import text_key
from app.services.analysis.answer_record import from_record_form, record_form
from app.services.analysis.model_view import JobModel, sampling_of
from app.services.analysis.pipeline import Engine
from app.services.analysis.saved_answers import Reuse, SavedAnswers
from app.services.analysis.steps import PHASES, record_steps
from app.services.search_index import SearchIndex, search_index_not_ready

logger = logging.getLogger("app.analysis")

DEFAULT_CONCURRENCY = 4
DEFAULT_QUEUE_LIMIT = 20
KEEPALIVE_SECONDS = 15.0
MAX_STREAMS_PER_USER = 5
RATE_LIMIT = 30
RATE_LIMIT_PER_ADDRESS = 120
RATE_WINDOW_SECONDS = 60.0
CANCEL_WAIT_SECONDS = 5.0
SHUTDOWN_WAIT_SECONDS = 20.0
TERMINAL_JOBS_KEPT = 500
QUEUE_STEP = "Sırada bekleme"
# What the trace tells about a keyed step (trace.Trace.listener).
STARTED, FINISHED, ERROR = "started", "finished", "error"
STOPPED_EVENT = "Durduruldu"


class SnapshotSource(Protocol):
    """The model connection an analysis reads once when it starts (llm-connection)."""

    port: LlmChatPort

    async def snapshot(
        self, *, tenant_id: int, tenant_public_id: str
    ) -> LlmConnection | LlmOutcome: ...

    async def model_state(self, *, tenant_id: int, tenant_public_id: str) -> ModelState: ...


@dataclass(frozen=True, slots=True)
class Asker:
    """Who owns a job: an account (``user_id``) or a visitor (``visitor_id``), never both
    (application-foundation 003-anonymous-visitor Decision 5). ``public_id`` is the owner's own
    public id; a visitor also brings its address and host name of the moment (Requirement 7)."""

    user_id: int | None
    public_id: str
    display_name: str
    visitor_id: int | None = None
    address: str | None = None
    host: str | None = None


@dataclass(frozen=True, slots=True)
class ListTerm:
    """A term of a term list (list-search): the list's id, its file name, the term's position."""

    list_public_id: str
    file_name: str
    position: int


@dataclass(frozen=True, slots=True)
class Tenant:
    tenant_id: int
    public_id: str


@dataclass(frozen=True, slots=True)
class Event:
    id: int
    type: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class OverlayContext:
    """What answer-feedback needs to apply the votes to an answer for the reading user: the
    answer's question and the time it was written (its first analysis's for a saved answer)."""

    tenant_id: int
    user_public_id: str
    query: str
    generated_at: str


class AnswerOverlay(Protocol):
    """answer-feedback's vote overlay on a result being read (question-analysis Requirement 7)."""

    async def apply(self, answer: dict[str, Any], context: OverlayContext) -> dict[str, Any]: ...


@dataclass(eq=False)
class AnalysisJob:
    public_id: str
    tenant: Tenant
    asker: Asker
    origin: Origin
    list_term: ListTerm | None
    query: str
    top: int
    fresh: bool
    accepted_at: datetime
    accepted_perf: float
    timeline: trace.Trace
    text_key: str
    state: JobState = JobState.QUEUED
    flow: Flow | None = None
    error: tuple[str, str] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step: str | None = None
    ahead: int = 0
    token: cancel.Token = field(default_factory=cancel.Token)
    events: list[Event] = field(default_factory=list)
    subscribers: set[asyncio.Queue[Event | None]] = field(default_factory=set)
    result: AnalysisResult | None = None
    engine: Engine | None = None
    model: str = ""
    dictionary_version: str = ""
    record_written: bool = False
    interrupting: bool = False
    queue_span: trace.Span | None = None
    reuse: Reuse | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def last_event_id(self) -> int:
        return self.events[-1].id if self.events else 0


@dataclass(frozen=True, slots=True)
class JobView:
    """A job as the endpoints show it: from memory while it runs, from its record after."""

    public_id: str
    owner_public_id: str
    state: JobState
    origin: Origin
    query: str
    fresh: bool
    ahead: int | None
    step: str | None
    flow: Flow | None
    error: tuple[str, str] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: AnalysisResult | None
    job: AnalysisJob | None

    def envelope(self) -> dict[str, Any]:
        return {
            "analysis_id": self.public_id,
            "state": self.state.value,
            "origin": self.origin.value,
            "query": self.query,
            "fresh": self.fresh,
            "ahead": self.ahead if self.state is JobState.QUEUED else None,
            "step": self.step if self.state is JobState.RUNNING else None,
            "flow": self.flow.value if self.flow and self.state is JobState.COMPLETED else None,
            "error": {"code": self.error[0], "message": self.error[1]} if self.error else None,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def analysis_not_found() -> ApplicationError:
    return ApplicationError(404, "analysis_not_found", "Analiz bulunamadı.")


def _unavailable() -> ApplicationError:
    return ApplicationError(
        503,
        "analysis_unavailable",
        "Uygulama yeniden başlıyor; biraz sonra yeniden deneyin.",
        headers={"Retry-After": "10"},
    )


def _queue_full() -> ApplicationError:
    return ApplicationError(
        503,
        "analysis_queue_full",
        "Şu anda çok sayıda analiz sırada; biraz sonra yeniden deneyin.",
        headers={"Retry-After": "30"},
    )


def _rate_limited() -> ApplicationError:
    return ApplicationError(
        429,
        "rate_limited",
        "Çok sık soru gönderildi; bir dakika sonra yeniden deneyin.",
        headers={"Retry-After": "60"},
    )


def too_many_streams() -> ApplicationError:
    return ApplicationError(
        429,
        "too_many_streams",
        "Çok sayıda açık izleme bağlantısı var; diğer sekmeleri kapatın.",
    )


def _ms(seconds: float) -> int:
    return max(0, round(seconds * 1000))


def _flow_of(result: AnalysisResult) -> Flow:
    if result.reused_at:
        return Flow.REUSED
    return Flow.ANALYST if result.analyst else Flow.UNAVAILABLE


class AnalysisJobs:
    """The process's analysis jobs and their queue (one backend replica, Decision 2)."""

    def __init__(
        self,
        *,
        index: SearchIndex,
        models: SnapshotSource,
        session_factory: async_sessionmaker[AsyncSession],
        saved_answers: SavedAnswers,
        overlay: AnswerOverlay,
        concurrency: int = DEFAULT_CONCURRENCY,
        queue_limit: int = DEFAULT_QUEUE_LIMIT,
        keepalive_seconds: float = KEEPALIVE_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.index = index
        self.models = models
        self.saved_answers = saved_answers
        self.overlay = overlay
        self._session_factory = session_factory
        self.concurrency = concurrency
        self.queue_limit = queue_limit
        self.keepalive_seconds = keepalive_seconds
        self._clock = clock
        self.accepting = True
        self.started_at = clock()
        self._jobs: dict[str, AnalysisJob] = {}
        self._finished: deque[str] = deque()
        self._waiting: deque[AnalysisJob] = deque()
        self._running: set[AnalysisJob] = set()
        self._tasks: dict[AnalysisJob, asyncio.Task[None]] = {}
        self._requests: dict[str, deque[float]] = {}
        self._address_starts = SlidingWindow(
            limit=RATE_LIMIT_PER_ADDRESS, window_seconds=RATE_WINDOW_SECONDS
        )
        self._streams: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None

    # ------------------------------------------------------------------ helpers

    def _bind_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop, self._loop_thread = loop, threading.get_ident()
        return loop

    def _on_loop(self, call: Callable[[], None]) -> None:
        """Run ``call`` on the event loop: at once from its thread, else scheduled there."""

        if threading.get_ident() == self._loop_thread or self._loop is None:
            call()
            return
        with contextlib.suppress(RuntimeError):  # the loop is already closed
            self._loop.call_soon_threadsafe(call)

    def _emit(self, job: AnalysisJob, kind: str, data: dict[str, Any] | None = None) -> None:
        event = Event(job.last_event_id + 1, kind, {"type": kind, **(data or {})})
        job.events.append(event)
        for queue in list(job.subscribers):
            queue.put_nowait(event)

    def _elapsed_ms(self, job: AnalysisJob) -> int:
        return _ms(time.perf_counter() - job.accepted_perf)

    def _listener(self, job: AnalysisJob) -> Callable[[trace.Span, str], None]:
        """Keyed steps become step events, OpenTelemetry step spans and step durations."""

        spans: dict[int, telemetry.StepSpan] = {}

        def heard(span: trace.Span, what: str) -> None:
            if span.key != "queue":
                if what == STARTED:
                    spans[span.id] = telemetry.open_step_span(span.key)
                else:
                    opened = spans.pop(span.id, None)
                    if opened is not None:
                        telemetry.close_step_span(opened, error=what == ERROR)
            seconds = (span.end - span.start) if span.end is not None else 0.0
            if what != STARTED:
                telemetry.record_analysis_step(span.key, seconds)

            def post() -> None:
                if what == STARTED:
                    job.step = span.key
                data = {"key": span.key, "status": what, "elapsed_ms": _ms(seconds)}
                self._emit(job, "step", data)

            self._on_loop(post)

        return heard

    def _announcer(self, job: AnalysisJob) -> Callable[[str, list[dict[str, Any]]], None]:
        """The tables a stage found become a ``tables`` event: the map marks them on its radar."""

        def found(stage: str, tables: list[dict[str, Any]]) -> None:
            self._on_loop(lambda: self._emit(job, "tables", {"stage": stage, "tables": tables}))

        return found

    # ------------------------------------------------------------------ acceptance

    def check_rate(self, user_public_id: str, address: str | None = None) -> None:
        """Requirement 23: at most 30 starts per visitor and 120 per address in 60 seconds."""

        if address is not None and not self._address_starts.hit(address):
            raise _rate_limited()
        now = time.monotonic()
        seen = self._requests.setdefault(user_public_id, deque())
        while seen and now - seen[0] >= RATE_WINDOW_SECONDS:
            seen.popleft()
        if len(seen) >= RATE_LIMIT:
            raise _rate_limited()
        seen.append(now)

    def ready(self) -> None:
        if not self.accepting:
            raise _unavailable()
        if not self.index.is_serving:
            raise search_index_not_ready()

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
        """Accept one analysis: completed at once with a saved answer, otherwise queued."""

        self._bind_loop()
        self.ready()
        job = AnalysisJob(
            public_id=new_public_id(),
            tenant=tenant,
            asker=asker,
            origin=origin,
            list_term=list_term,
            query=query,
            top=top,
            fresh=fresh,
            accepted_at=self._clock(),
            accepted_perf=time.perf_counter(),
            timeline=trace.Trace(),
            text_key=text_key(query),
        )
        job.timeline.listener = self._listener(job)
        job.timeline.announcer = self._announcer(job)
        if not fresh:
            engine = self.index.engine()
            connection = await self.models.snapshot(
                tenant_id=tenant.tenant_id, tenant_public_id=tenant.public_id
            )
            with trace.recording(job.timeline):
                reuse = await self._lookup(job, engine, connection)
            if reuse is not None:
                job.engine = engine
                job.dictionary_version = engine.dictionary.version
                job.reuse = reuse
                await self._insert(job)
                self._jobs[job.public_id] = job
                self._accepted(job)
                with telemetry.analysis_run_span(origin.value) as run:
                    await self._complete(job, reuse.result, run)
                return job
        if origin is Origin.QUESTION and len(self._waiting) >= self.queue_limit:
            raise _queue_full()  # a list term enters the queue alone, never refused (Req. 9 c)
        job.ahead = len(self._running) + len(self._waiting)
        job.queue_span = job.timeline.open(QUEUE_STEP, None, trace.STEP, "önceki analizin bitmesi")
        job.queue_span.key = "queue"
        await self._insert(job)
        self._jobs[job.public_id] = job
        self._waiting.append(job)
        telemetry.analysis_queue_changed(1)
        self._accepted(job)
        self._emit(job, "queued", {"ahead": job.ahead})
        job.timeline.notify(job.queue_span, STARTED)
        self._pump()
        return job

    @staticmethod
    def _accepted(job: AnalysisJob) -> None:
        log_event(
            logger,
            "analysis.accepted",
            analysis_id=job.public_id,
            origin=job.origin.value,
            fresh=job.fresh,
            ahead=job.ahead,
        )

    async def _lookup(
        self, job: AnalysisJob, engine: Engine, connection: LlmConnection | LlmOutcome
    ) -> Reuse | None:
        keys = await asyncio.to_thread(engine.cache_keys, job.query)
        fingerprint = engine.cache_fingerprint(job.top, sampling_of(connection))
        return await self.saved_answers.lookup(
            job.tenant.tenant_id, engine, job.query, keys, fingerprint
        )

    # ------------------------------------------------------------------ the queue

    def _blocked(self, job: AnalysisJob) -> bool:
        """Requirement 14: a job waits while the same question runs on the same engine."""

        if job.fresh or not self.index.is_serving:
            return False
        serving = self.index.engine()
        return any(
            other.text_key == job.text_key and other.top == job.top and other.engine is serving
            for other in self._running
        )

    def _owner_busy(self, job: AnalysisJob) -> bool:
        """Requirement 9 b, Decision 27: an owner runs at most one job at a time."""

        owner = (job.tenant.tenant_id, job.asker.public_id)
        return any(
            (other.tenant.tenant_id, other.asker.public_id) == owner for other in self._running
        )

    def _pump(self) -> None:
        if not self.accepting:
            return
        while len(self._running) < self.concurrency:
            nxt = next(
                (
                    job
                    for job in self._waiting
                    if not self._blocked(job) and not self._owner_busy(job)
                ),
                None,
            )
            if nxt is None:
                break
            self._waiting.remove(nxt)
            telemetry.analysis_queue_changed(-1)
            self._running.add(nxt)
            telemetry.analyses_running_changed(1)
            self._tasks[nxt] = asyncio.get_running_loop().create_task(self._run(nxt))
        self._refresh_ahead()

    def _refresh_ahead(self) -> None:
        for position, job in enumerate(self._waiting):
            ahead = len(self._running) + position
            if ahead != job.ahead:
                job.ahead = ahead
                self._emit(job, "queued", {"ahead": ahead})

    def _release(self, job: AnalysisJob) -> None:
        if job in self._running:
            self._running.discard(job)
            telemetry.analyses_running_changed(-1)
        self._tasks.pop(job, None)
        self._pump()

    # ------------------------------------------------------------------ running

    def _close_queue_step(self, job: AnalysisJob) -> None:
        span = job.queue_span
        if span is None or span.end is not None:
            return
        job.timeline.close(span)
        job.timeline.notify(span, FINISHED)
        accepted_ns = int(job.accepted_at.timestamp() * 1_000_000_000)
        telemetry.close_step_span(
            telemetry.open_step_span("queue", start_time_ns=accepted_ns, current=False),
            error=False,
        )

    async def _run(self, job: AnalysisJob) -> None:
        if job.terminal:  # stopped between leaving the queue and starting
            self._release(job)
            return
        job.state = JobState.RUNNING
        job.started_at = self._clock()
        wait_ms = _ms(time.perf_counter() - job.accepted_perf)
        self._emit(job, "started")
        try:
            with telemetry.analysis_run_span(job.origin.value) as run:
                self._close_queue_step(job)
                telemetry.record_analysis_started(job.origin.value, wait_ms / 1000)
                log_event(
                    logger, "analysis.started", analysis_id=job.public_id, queue_wait_ms=wait_ms
                )
                await self._write(
                    job,
                    "start",
                    {
                        "state": JobState.RUNNING.value,
                        "started_at": job.started_at,
                        "queue_wait_ms": wait_ms,
                    },
                    from_queued=True,
                )
                await self._analyse(job, run)
        finally:
            job.done.set()
            self._release(job)

    async def _analyse(self, job: AnalysisJob, run: telemetry.AnalysisRunRecord) -> None:
        try:
            with trace.recording(job.timeline), cancel.using(job.token):
                engine = self.index.engine()
                job.engine = engine
                job.dictionary_version = engine.dictionary.version
                connection = await self.models.snapshot(
                    tenant_id=job.tenant.tenant_id, tenant_public_id=job.tenant.public_id
                )
                model = JobModel(
                    self.models.port, connection, self._bind_loop(), job.token, job.public_id
                )
                job.model = model.model
                keys = await asyncio.to_thread(engine.cache_keys, job.query)
                fingerprint = engine.cache_fingerprint(job.top, sampling_of(connection))
                if not job.fresh:
                    reuse = await self.saved_answers.lookup(
                        job.tenant.tenant_id, engine, job.query, keys, fingerprint
                    )
                    if reuse is not None:
                        job.reuse = reuse
                        await self._complete(job, reuse.result, run)
                        return
                cancel.check()
                result = await asyncio.to_thread(engine.with_llm(model).analyze, job.query, job.top)
                cancel.check()
                if result.analyst:
                    if self.index.is_serving and self.index.engine() is engine:
                        await self.saved_answers.put(
                            job.tenant.tenant_id,
                            query=job.query,
                            keys=keys,
                            fingerprint=fingerprint,
                            result=result,
                            analysis_public_id=job.public_id if job.record_written else None,
                            user_id=job.asker.user_id,
                        )
                    else:
                        telemetry.record_saved_answer_write("skipped")
                await self._complete(job, result, run)
        except cancel.Cancelled:
            if job.interrupting:
                await self._end(job, JobState.INTERRUPTED, Flow.INTERRUPTED, run)
            else:
                with trace.recording(job.timeline):
                    trace.event(STOPPED_EVENT, "kullanıcı analizi durdurdu", status="error")
                await self._end(job, JobState.CANCELLED, Flow.CANCELLED, run)
        except Exception as error:  # noqa: BLE001 - any other failure ends the job as failed
            log_event(
                logger,
                "analysis.error",
                analysis_id=job.public_id,
                error_type=type(error).__name__,
            )
            await self._end(job, JobState.FAILED, Flow.FAILED, run)

    # ------------------------------------------------------------------ the end of a job

    async def _complete(
        self, job: AnalysisJob, result: AnalysisResult, run: telemetry.AnalysisRunRecord
    ) -> None:
        job.result = result
        await self._end(job, JobState.COMPLETED, _flow_of(result), run)

    async def _end(
        self,
        job: AnalysisJob,
        state: JobState,
        flow: Flow,
        run: telemetry.AnalysisRunRecord | None,
    ) -> None:
        if job.terminal:
            return
        self._close_queue_step(job)
        job.state, job.flow = state, flow
        job.finished_at = self._clock()
        job.step = None
        if state is JobState.FAILED:
            job.error = (FAILED_CODE, FAILED_MESSAGE)
        elif state is JobState.CANCELLED:
            job.error = (CANCELLED_CODE, CANCELLED_MESSAGE)
        elif state is JobState.INTERRUPTED:
            job.error = (INTERRUPTED_CODE, INTERRUPTED_MESSAGE)
        if job in self._waiting:
            self._waiting.remove(job)
            telemetry.analysis_queue_changed(-1)
        recorded = record_steps(job.timeline.to_list())
        result = job.result
        duration_ms = _ms(time.perf_counter() - job.accepted_perf)
        verdict = result.verdict.value if result is not None else ""
        dropped = result.dropped_by_validation if result is not None else 0
        if run is not None:
            run.outcome = flow.value
            run.verdict = verdict
            run.suggestions = len(result.objects) if result is not None else 0
            run.dropped = dropped
            run.llm_calls = recorded.llm_calls
        values = self._final_values(job, recorded, duration_ms)
        await self._write(job, "finish", values)
        telemetry.record_analysis_finished(
            origin=job.origin.value,
            outcome=flow.value,
            duration_seconds=duration_ms / 1000,
            verdict=verdict,
            dropped=dropped,
        )
        log_event(
            logger,
            "analysis.finished",
            analysis_id=job.public_id,
            origin=job.origin.value,
            outcome=flow.value,
            verdict=verdict or None,
            suggestions=len(result.objects) if result is not None else 0,
            dropped=dropped,
            llm_calls=recorded.llm_calls,
            prompt_tokens=recorded.prompt_tokens,
            completion_tokens=recorded.completion_tokens,
            duration_ms=duration_ms,
            error_code=job.error[0] if job.error else None,
        )
        if state is JobState.COMPLETED:
            self._emit(job, "completed", {"flow": flow.value, "verdict": verdict})
        elif state is JobState.FAILED and job.error is not None:
            self._emit(job, "failed", {"code": job.error[0], "message": job.error[1]})
        else:
            self._emit(job, state.value)
        for queue in list(job.subscribers):
            queue.put_nowait(None)
        job.done.set()
        self._finished.append(job.public_id)
        while len(self._finished) > TERMINAL_JOBS_KEPT:
            self._jobs.pop(self._finished.popleft(), None)

    def _final_values(self, job: AnalysisJob, recorded: Any, duration_ms: int) -> dict[str, Any]:
        result = job.result
        flow = job.flow
        model = job.model
        if result is not None:
            model = result.llm_model or model
        keys = [m.object_key for m in result.objects][:MAX_TABLE_KEYS] if result else []
        summary = result.summary[:SUMMARY_MAX_CHARS] if result else ""
        reuse = job.reuse if flow is Flow.REUSED else None
        list_name = job.list_term.file_name if job.list_term else ""
        values: dict[str, Any] = {
            "state": job.state.value,
            "flow": flow.value if flow else None,
            "finished_at": job.finished_at,
            "duration_ms": duration_ms,
            "model": model[:256],
            "dictionary_version": (job.dictionary_version or "")[:64],
            "verdict": result.verdict.value if result else None,
            "summary": summary,
            "table_keys": keys,
            "result": record_form(result) if result is not None else None,
            "unavailable_reason": (
                result.fallback[:REASON_MAX_CHARS] if result and flow is Flow.UNAVAILABLE else ""
            ),
            "reused_at": reuse.answered_at if reuse else None,
            "reused_query": reuse.query if reuse else None,
            "reused_match": reuse.match.value if reuse else None,
            "error_code": job.error[0] if job.error else None,
            "error_message": job.error[1][:ERROR_MESSAGE_MAX_CHARS] if job.error else None,
            "llm_calls": recorded.llm_calls,
            "prompt_tokens": recorded.prompt_tokens,
            "completion_tokens": recorded.completion_tokens,
            "steps": recorded.steps,
            "steps_truncated": recorded.truncated,
            "search_key": fold(" ".join([job.query, model, summary, list_name, *keys])),
        }
        for name, _keys in PHASES:
            values[f"phase_{name}_ms"] = recorded.phases[name]
        if result is not None and job.engine is not None and not job.dictionary_version:
            values["dictionary_version"] = job.engine.dictionary.version[:64]
        return values

    # ------------------------------------------------------------------ the record

    async def _insert(self, job: AnalysisJob) -> None:
        term = job.list_term
        record = AnalysisRecord(
            public_id=job.public_id,
            tenant_id=job.tenant.tenant_id,
            asked_by=job.asker.user_id,
            asked_by_visitor_id=job.asker.visitor_id,
            client_address=job.asker.address,
            client_host=job.asker.host,
            state=JobState.QUEUED.value,
            asked_at=job.accepted_at,
            query=job.query,
            fresh=job.fresh,
            origin=job.origin.value,
            list_public_id=term.list_public_id if term else None,
            list_file_name=term.file_name if term else None,
            list_position=term.position if term else None,
            created_by=job.asker.user_id,
            updated_by=job.asker.user_id,
        )
        try:
            async with self._session_factory() as session:
                await AnalysisRecordRepository(session).add(record)
                await session.commit()
        except Exception as error:  # noqa: BLE001 - the analysis goes on without its record
            self._write_failed(job, "accept", error)
            return
        job.record_written = True

    async def _write(
        self, job: AnalysisJob, stage: str, values: dict[str, Any], *, from_queued: bool = False
    ) -> None:
        if not job.record_written:
            return
        try:
            async with self._session_factory() as session:
                await AnalysisRecordRepository(session).update_unfinished(
                    job.tenant.tenant_id, job.public_id, values, from_queued=from_queued
                )
                await session.commit()
        except Exception as error:  # noqa: BLE001 - the answer is still served from memory
            self._write_failed(job, stage, error)

    @staticmethod
    def _write_failed(job: AnalysisJob, stage: str, error: BaseException) -> None:
        log_event(
            logger,
            "analysis.record_write_failed",
            analysis_id=job.public_id,
            stage=stage,
            error_type=type(error).__name__,
        )

    async def interrupt_leftovers(self) -> int:
        """Requirement 12: records left queued or running by an earlier process."""

        async with self._session_factory() as session:
            count = await AnalysisRecordRepository(session).interrupt_unfinished(
                self.started_at,
                {
                    "state": JobState.INTERRUPTED.value,
                    "flow": Flow.INTERRUPTED.value,
                    "finished_at": self._clock(),
                    "error_code": INTERRUPTED_CODE,
                    "error_message": INTERRUPTED_MESSAGE,
                },
            )
            await session.commit()
        log_event(logger, "analysis.interrupted_at_startup", count=count)
        return count

    async def run_startup(self, database_ready: Callable[[], Any]) -> None:
        while not await database_ready():
            await asyncio.sleep(1.0)
        try:
            await self.interrupt_leftovers()
        except Exception as error:  # noqa: BLE001 - logged; the next start tries again
            log_event(logger, "analysis.startup_failed", error_type=type(error).__name__)

    async def shutdown(self, wait_seconds: float = SHUTDOWN_WAIT_SECONDS) -> None:
        """Requirement 12: refuse new jobs; queued and running jobs end as interrupted."""

        self.accepting = False
        for job in list(self._waiting):
            await self._end(job, JobState.INTERRUPTED, Flow.INTERRUPTED, None)
        running = list(self._tasks.items())
        for job, _task in running:
            job.interrupting = True
            job.token.cancel()
        if running:
            await asyncio.wait([task for _job, task in running], timeout=wait_seconds)
        for job, task in running:
            if not job.terminal:
                task.cancel()
                await self._end(job, JobState.INTERRUPTED, Flow.INTERRUPTED, None)

    # ------------------------------------------------------------------ reading

    def active(self, user_public_id: str) -> AnalysisJob | None:
        """The user's most recently accepted single question that is queued or running."""

        jobs = [
            job
            for job in (*self._running, *self._waiting)
            if job.asker.public_id == user_public_id and job.origin is Origin.QUESTION
        ]
        return max(jobs, key=lambda job: job.accepted_perf, default=None)

    def view_of(self, job: AnalysisJob) -> JobView:
        return JobView(
            public_id=job.public_id,
            owner_public_id=job.asker.public_id,
            state=job.state,
            origin=job.origin,
            query=job.query,
            fresh=job.fresh,
            ahead=job.ahead,
            step=job.step,
            flow=job.flow,
            error=job.error,
            created_at=job.accepted_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            result=job.result,
            job=job,
        )

    async def find(self, tenant_id: int, user_public_id: str, public_id: str) -> JobView:
        """The caller's own job; 404 for another user's job, a deleted record or none."""

        job = self._jobs.get(public_id)
        row: RecordRow | None = None
        try:
            async with self._session_factory() as session:
                row = await AnalysisRecordRepository(session).owned_by(tenant_id, public_id)
        except Exception as error:
            log_event(logger, "analysis.record_read_failed", error_type=type(error).__name__)
            if job is None:
                raise
        else:
            if row is None and (job is None or job.record_written):
                raise analysis_not_found()
        if row is not None:
            if row.asker_public_id != user_public_id:
                raise analysis_not_found()
            if job is None or JobState(row.record.state) in TERMINAL_STATES:
                return self._view_of_record(row, job)
        if job is None or job.asker.public_id != user_public_id:
            raise analysis_not_found()
        return self.view_of(job)

    @staticmethod
    def _view_of_record(row: RecordRow, job: AnalysisJob | None) -> JobView:
        r = row.record
        state = JobState(r.state)
        error = (r.error_code, r.error_message or "") if r.error_code else None
        result = from_record_form(r.result) if r.result is not None else None
        return JobView(
            public_id=r.public_id,
            owner_public_id=row.asker_public_id,
            state=state,
            origin=Origin(r.origin),
            query=r.query,
            fresh=r.fresh,
            ahead=job.ahead if job is not None else None,
            step=job.step if job is not None else None,
            flow=Flow(r.flow) if r.flow else None,
            error=error,
            created_at=r.asked_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
            result=result,
            job=job,
        )

    async def answer(self, tenant_id: int, user_public_id: str, view: JobView) -> dict[str, Any]:
        """Requirement 7: the result for the reading user, with answer-feedback's overlay."""

        if view.result is None:
            raise analysis_not_found()
        return await self.present(tenant_id, user_public_id, view.result, view.public_id)

    async def present(
        self, tenant_id: int, user_public_id: str, result: AnalysisResult, analysis_id: str | None
    ) -> dict[str, Any]:
        """An answer in its Requirement 7 form with the votes applied for the reading user (also
        a list term's answer, list-search Requirement 12); an overlay failure returns the answer
        without votes and leaves an event."""

        data = serialize.analysis(result)
        context = OverlayContext(
            tenant_id=tenant_id,
            user_public_id=user_public_id,
            query=result.query,
            generated_at=result.generated_at,
        )
        try:
            return await self.overlay.apply(data, context)
        except Exception:  # noqa: BLE001 - votes must never cost the answer
            log_event(logger, "analysis.feedback_overlay_failed", analysis_id=analysis_id)
            return data

    async def cancel(self, view: JobView) -> JobView:
        """Requirement 11: a queued job leaves the queue at once, a running job stops within
        seconds; a finished job stays as it is."""

        job = view.job
        if job is None or job.terminal or view.state in TERMINAL_STATES:
            return view
        if job.state is JobState.QUEUED and job in self._waiting:
            with trace.recording(job.timeline):
                trace.event(STOPPED_EVENT, "kullanıcı analizi durdurdu", status="error")
            await self._end(job, JobState.CANCELLED, Flow.CANCELLED, None)
            self._pump()
            return self.view_of(job)
        job.token.cancel()
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(CANCEL_WAIT_SECONDS):
                await job.done.wait()
        return self.view_of(job)

    # ------------------------------------------------------------------ live progress

    def open_stream(self, user_public_id: str) -> None:
        if self._streams.get(user_public_id, 0) >= MAX_STREAMS_PER_USER:
            raise too_many_streams()
        self._streams[user_public_id] = self._streams.get(user_public_id, 0) + 1
        telemetry.analysis_streams_changed(1)

    def close_stream(self, user_public_id: str) -> None:
        left = self._streams.get(user_public_id, 0) - 1
        if left > 0:
            self._streams[user_public_id] = left
        else:
            self._streams.pop(user_public_id, None)
        telemetry.analysis_streams_changed(-1)

    def _snapshot(self, view: JobView, last_id: int) -> Event:
        job = view.job
        elapsed = self._elapsed_ms(job) if job is not None and not job.terminal else None
        if elapsed is None and view.finished_at is not None:
            elapsed = _ms((view.finished_at - view.created_at).total_seconds())
        data = {
            "type": "snapshot",
            "analysis_id": view.public_id,
            "state": view.state.value,
            "ahead": view.ahead if view.state is JobState.QUEUED else None,
            "step": view.step if view.state is JobState.RUNNING else None,
            "elapsed_ms": elapsed or 0,
        }
        return Event(last_id, "snapshot", data)

    @staticmethod
    def _final_event(view: JobView, event_id: int) -> Event:
        if view.state is JobState.COMPLETED:
            verdict = view.result.verdict.value if view.result is not None else ""
            data: dict[str, Any] = {
                "type": "completed",
                "flow": view.flow.value if view.flow else "",
                "verdict": verdict,
            }
        elif view.state is JobState.FAILED:
            code, message = view.error or (FAILED_CODE, FAILED_MESSAGE)
            data = {"type": "failed", "code": code, "message": message}
        else:
            data = {"type": view.state.value}
        return Event(event_id, data["type"], data)

    async def events(
        self,
        view: JobView,
        *,
        last_event_id: int | None,
        expires_at: float | None,
        clock: Callable[[], float] = time.time,
    ) -> AsyncIterator[str]:
        """Requirement 10: ``snapshot`` first, then the missed step events after
        ``Last-Event-ID``, then live events and a ``: canlı`` line every 15 seconds without one;
        the stream closes after the final event or when the access token expires."""

        job = view.job
        if job is None or (view.state in TERMINAL_STATES and not job.terminal):
            last = (job.last_event_id if job is not None else 0) + 1
            yield _frame(self._snapshot(view, last))
            if view.state in TERMINAL_STATES:
                yield _frame(self._final_event(view, last + 1))
            return
        queue: asyncio.Queue[Event | None] = asyncio.Queue()
        replay = [e for e in job.events if last_event_id is not None and e.id > last_event_id]
        if not job.terminal:
            job.subscribers.add(queue)
        try:
            yield _frame(self._snapshot(self.view_of(job), job.last_event_id))
            for event in replay:
                if event.type in ("completed", "failed", "cancelled", "interrupted"):
                    continue
                yield _frame(event)
            if job.terminal:
                yield _frame(job.events[-1])
                return
            while True:
                timeout = self.keepalive_seconds
                if expires_at is not None:
                    left = expires_at - clock()
                    if left <= 0:
                        return
                    timeout = min(timeout, left)
                try:
                    async with asyncio.timeout(timeout):
                        live = await queue.get()
                except TimeoutError:
                    yield ": canlı\n\n"
                    continue
                if live is None:
                    return
                yield _frame(live)
                if live.type in ("completed", "failed", "cancelled", "interrupted"):
                    return
        finally:
            job.subscribers.discard(queue)


def _frame(event: Event) -> str:
    body = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"id: {event.id}\ndata: {body}\n\n"
