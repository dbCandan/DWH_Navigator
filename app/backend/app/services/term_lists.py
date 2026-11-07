"""Term lists: upload, the background run, stop, resume, interruption and reports
(data-dictionary 005-list-search Requirement 1-16, 18, 19, Decision 2-6, 8, 10, 12-14).

A list is read with the shared safe Excel reader and written with its terms in one transaction.
Its run is a background task of this process that hands one term at a time to question-analysis's
job queue (``AnalysisJobs.start`` with origin ``list``) and waits for that job to end before the
next term enters the queue, so a single question waits for at most the term that runs. Every
term's answer is written as soon as the term ends, in full and independent of the dictionary. A
stop cuts the running term's model calls through its job; a closing process, a process that died
and a run that ended unexpectedly all leave the list "yarıda kesildi"; nothing resumes by itself.
The list lives in PostgreSQL, so closing the page changes nothing.

Nothing here logs or traces a term, a file name, a header, an answer, a table or a column name.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import telemetry
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.domain.analysis import AnalysisResult, ListItem, ListResult
from app.domain.analysis_records import ERROR_MESSAGE_MAX_CHARS, Flow, JobState, Origin
from app.domain.models.term_list import TermList, TermListItem
from app.domain.term_lists import (
    TERM_ERROR_CODE,
    TERM_ERROR_MESSAGE,
    TERM_TOP,
    ListStatus,
    TermListRejected,
    TermState,
)
from app.infrastructure.repositories.term_list_repository import (
    ListRow,
    TermListRepository,
)
from app.services.analysis.answer_record import from_record_form, record_form
from app.services.analysis.dictionary_workbook import SOURCE_NAME
from app.services.analysis.jobs import AnalysisJob, Asker, JobView, ListTerm, Tenant
from app.services.analysis.loader import load_term_list
from app.services.analysis.pipeline import ISTANBUL
from app.services.analysis.report.excel import (
    report_filename,
    write_ask_report,
    write_list_report,
)
from app.services.search_index import SearchIndex

logger = logging.getLogger("app.lists")

CANCEL_WAIT_SECONDS = 5.0
CHECK_SECONDS = 60.0
SHUTDOWN_WAIT_SECONDS = 5.0
_STOPPED = {ListStatus.CANCELLED.value, ListStatus.INTERRUPTED.value}


class TermAnalyses(Protocol):
    """What a list needs from question-analysis's jobs."""

    accepting: bool
    index: SearchIndex

    def ready(self) -> None: ...

    async def present(
        self, tenant_id: int, user_public_id: str, result: AnalysisResult, analysis_id: str | None
    ) -> dict[str, Any]: ...

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
    ) -> AnalysisJob: ...

    def view_of(self, job: AnalysisJob) -> JobView: ...

    async def cancel(self, view: JobView) -> JobView: ...


def term_list_not_found() -> ApplicationError:
    return ApplicationError(404, "term_list_not_found", "Kayıt bulunamadı")


def term_not_answered() -> ApplicationError:
    return ApplicationError(404, "term_list_item_not_answered", "Kayıt bulunamadı")


def _running() -> ApplicationError:
    """The caller already has a running list (Decision 3; another owner's list is not an engel)."""

    return ApplicationError(
        409,
        "term_list_running",
        "Bir liste zaten çalışıyor; bitmesini bekleyin ya da durdurun.",
    )


def _nothing_to_resume() -> ApplicationError:
    return ApplicationError(
        409,
        "term_list_nothing_to_resume",
        "Bu listenin bütün terimleri cevaplandı; devam edecek terim yok.",
    )


def _ms(seconds: float) -> int:
    return max(0, round(seconds * 1000))


@dataclass(eq=False)
class Run:
    """A list running in this process."""

    term_list_id: int
    public_id: str
    file_name: str
    tenant: Tenant
    owner: Asker
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    job: AnalysisJob | None = None
    task: asyncio.Task[None] | None = None
    cursor: int = 0


def _best(answer: dict[str, Any] | None) -> dict[str, Any] | None:
    objects = answer.get("objects") if answer else None
    if not objects:
        return None
    m = objects[0]
    return {
        "key": m["object_key"],
        "name": m["object_name"],
        "score": round(m["score"], 4),
        "level": m["level"],
    }


def _item_state(row: TermList, item: TermListItem) -> TermState:
    if item.answer is not None:
        return TermState.ANSWERED
    if item.error_code is not None:
        return TermState.ERROR
    if row.status == ListStatus.RUNNING.value and item.position == row.current_position:
        return TermState.RUNNING
    if row.stop_requested or row.status in _STOPPED:
        return TermState.STOPPED
    return TermState.QUEUED


def _item_row(row: TermList, item: TermListItem) -> dict[str, Any]:
    answer = item.answer
    return {
        "position": item.position,
        "term": item.term,
        "state": _item_state(row, item).value,
        "verdict": answer["verdict"] if answer else "",
        "summary": answer["summary"] if answer else (item.error_message or ""),
        "missing": list(answer.get("missing") or []) if answer else [],
        "best": _best(answer),
        "flow": item.flow,
        "elapsed_ms": item.elapsed_ms,
    }


class TermLists:
    """The process's term lists: one may run per owner at a time; different owners run in
    parallel (Decision 3)."""

    def __init__(
        self,
        *,
        jobs: TermAnalyses,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        check_seconds: float = CHECK_SECONDS,
    ) -> None:
        self.jobs = jobs
        self._session_factory = session_factory
        self._clock = clock
        self.check_seconds = check_seconds
        self.started_at = clock()
        self.closing = False
        self._runs: dict[int, Run] = {}
        self._claimed: set[int] = set()

    # ------------------------------------------------------------------ reading

    async def _owned(self, tenant_id: int, owner_public_id: str, list_id: str) -> ListRow:
        """The caller's own list; anyone else's list is as if it did not exist."""

        async with self._session_factory() as session:
            row = await TermListRepository(session).find(tenant_id, list_id)
        if row is None or row.owner_public_id != owner_public_id:
            raise term_list_not_found()
        return row

    async def snapshot_of(self, row: ListRow) -> dict[str, Any]:
        """Requirement 7: the list and a row per term (no term's full answer)."""

        r = row.record
        async with self._session_factory() as session:
            items = await TermListRepository(session).items(r.term_list_id)
        now = self._clock()
        done = [i for i in items if i.answer is not None or i.error_code is not None]
        running = r.status == ListStatus.RUNNING.value
        elapsed = r.elapsed_before_ms
        if running and r.run_started_at is not None:
            elapsed += _ms((now - r.run_started_at).total_seconds())
        mean = sum(i.elapsed_ms for i in done) / len(done) if done else 0
        return {
            "id": r.public_id,
            "name": r.file_name,
            "owner": {"public_id": row.owner_public_id, "display_name": row.owner_display_name},
            "header": r.header,
            "notes": list(r.notes),
            "status": r.status,
            "stop_requested": r.stop_requested,
            "total": len(items),
            "done": len(done),
            "elapsed_ms": elapsed,
            "eta_ms": round(mean * (len(items) - len(done))) if running and done else None,
            "created_at": r.created_at,
            "finished_at": r.finished_at,
            "dictionary_version": r.dictionary_version,
            "items": [_item_row(r, i) for i in items],
        }

    async def snapshot(self, tenant_id: int, owner_public_id: str, list_id: str) -> dict[str, Any]:
        return await self.snapshot_of(await self._owned(tenant_id, owner_public_id, list_id))

    async def page(self, tenant_id: int, owner: Asker, page: int, page_size: int) -> dict[str, Any]:
        """Requirement 15: the caller's kept lists, newest first."""

        async with self._session_factory() as session:
            rows, total = await TermListRepository(session).page(
                tenant_id, owner.user_id, owner.visitor_id, page, page_size
            )
        return {
            "items": [
                {
                    "id": s.record.public_id,
                    "name": s.record.file_name,
                    "owner": {"public_id": s.owner_public_id, "display_name": s.owner_display_name},
                    "status": s.record.status,
                    "stop_requested": s.record.stop_requested,
                    "total": s.record.term_count,
                    "done": s.done,
                    "created_at": s.record.created_at,
                    "finished_at": s.record.finished_at,
                }
                for s in rows
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    async def _answered(
        self, tenant_id: int, owner_public_id: str, list_id: str, position: int
    ) -> tuple[ListRow, Any]:
        row = await self._owned(tenant_id, owner_public_id, list_id)
        async with self._session_factory() as session:
            item = await TermListRepository(session).item(row.record.term_list_id, position)
        if item is None or item.answer is None:
            raise term_not_answered()
        result = from_record_form(item.answer)
        if result is None:  # pragma: no cover - the kept form is written by this module
            raise RuntimeError("term answer unreadable")
        return row, result

    async def item(
        self, tenant_id: int, owner_public_id: str, list_id: str, position: int
    ) -> dict[str, Any]:
        """Requirement 12: the term's full answer, the votes applied for its owner."""

        _row, result = await self._answered(tenant_id, owner_public_id, list_id, position)
        return await self.jobs.present(tenant_id, owner_public_id, result, None)

    async def item_report(
        self, tenant_id: int, owner_public_id: str, list_id: str, position: int
    ) -> tuple[str, bytes]:
        """The term's single-question report, made from its kept answer."""

        row, result = await self._answered(tenant_id, owner_public_id, list_id, position)
        data = await asyncio.to_thread(write_ask_report, result)
        self._downloaded(row, "item")
        return report_filename("ask", result.query, self._clock().astimezone(ISTANBUL)), data

    async def report(self, tenant_id: int, owner_public_id: str, list_id: str) -> tuple[str, bytes]:
        """Requirement 13: one workbook for the whole list, made now from the kept answers."""

        row = await self._owned(tenant_id, owner_public_id, list_id)
        r = row.record
        async with self._session_factory() as session:
            items = await TermListRepository(session).items(r.term_list_id)
        now = self._clock().astimezone(ISTANBUL)

        def build() -> bytes:
            result = ListResult(
                name=r.file_name,
                items=[
                    ListItem(
                        index=i.position,
                        term=i.term,
                        result=from_record_form(i.answer) if i.answer is not None else None,
                        error=i.error_message or "",
                        elapsed_ms=i.elapsed_ms,
                    )
                    for i in items
                ],
                dictionary_source=SOURCE_NAME,
                dictionary_version=r.dictionary_version,
                generated_at=now.strftime("%Y-%m-%d %H:%M"),
                cancelled=r.status in _STOPPED,
                header=r.header,
                notes=list(r.notes),
            )
            return write_list_report(result)

        data = await asyncio.to_thread(build)
        self._downloaded(row, "list")
        stem = PurePosixPath(r.file_name).stem
        return report_filename("liste", stem, now), data

    @staticmethod
    def _downloaded(row: ListRow, kind: str) -> None:
        telemetry.record_term_list_report(kind)
        log_event(logger, "term_list.report_downloaded", list_id=row.record.public_id, kind=kind)

    # ------------------------------------------------------------------ starting

    async def refuse_while_running(self, tenant: Tenant, owner: Asker) -> None:
        """Requirement 4: the caller's own running list refuses a new one, before reading;
        another owner's running list is not an engel (Decision 3)."""

        async with self._session_factory() as session:
            running = await TermListRepository(session).running_for_owner(
                tenant.tenant_id, owner.user_id, owner.visitor_id
            )
        if running is not None:
            telemetry.record_term_list_upload_rejected("term_list_running")
            log_event(logger, "term_list.upload_rejected", code="term_list_running")
            raise _running()

    async def start(
        self, *, tenant: Tenant, owner: Asker, file_name: str, data: bytes
    ) -> dict[str, Any]:
        """Read the list, keep it with its terms and start it at once."""

        await self.refuse_while_running(tenant, owner)
        self.jobs.ready()
        try:
            terms = await asyncio.to_thread(load_term_list, data)
        except TermListRejected as rejected:
            telemetry.record_term_list_upload_rejected(rejected.code.value)
            log_event(logger, "term_list.upload_rejected", code=rejected.code.value)
            raise ApplicationError(422, rejected.code.value, rejected.message) from None
        record = TermList(
            tenant_id=tenant.tenant_id,
            owner_id=owner.user_id,
            owner_visitor_id=owner.visitor_id,
            client_address=owner.address,
            client_host=owner.host,
            file_name=file_name,
            header=terms.header,
            notes=list(terms.notes),
            status=ListStatus.RUNNING.value,
            stop_requested=False,
            term_count=len(terms.terms),
            dictionary_version=self.jobs.index.engine().dictionary.version[:64],
            run_started_at=self._clock(),
            elapsed_before_ms=0,
            created_by=owner.user_id,
            updated_by=owner.user_id,
        )
        try:
            async with self._session_factory() as session:
                await TermListRepository(session).add(record, terms.terms)
                await session.commit()
                term_list_id, public_id = record.term_list_id, record.public_id
                self._claimed.add(term_list_id)
        except IntegrityError:
            await self.refuse_while_running(tenant, owner)
            raise  # pragma: no cover - the unique running row is the only constraint here
        run = Run(term_list_id, public_id, file_name, tenant, owner)
        self._begin(run)
        telemetry.record_term_list_started()
        log_event(
            logger,
            "term_list.started",
            list_id=public_id,
            owner_public_id=owner.public_id,
            terms=len(terms.terms),
        )
        return await self.snapshot(tenant.tenant_id, owner.public_id, public_id)

    def _begin(self, run: Run) -> None:
        self._runs[run.term_list_id] = run
        self._claimed.discard(run.term_list_id)
        telemetry.term_lists_running_changed(1)
        run.task = asyncio.get_running_loop().create_task(self._run(run))

    # ------------------------------------------------------------------ the run

    async def _write(self, term_list_id: int, position: int | None, **values: Any) -> None:
        async with self._session_factory() as session:
            repository = TermListRepository(session)
            item_values = values.pop("item", None)
            if position is not None and item_values is not None:
                await repository.set_item(term_list_id, position, **item_values)
            await repository.set_list(term_list_id, **values)
            await session.commit()

    async def _next(self, run: Run) -> TermListItem | None:
        async with self._session_factory() as session:
            return await TermListRepository(session).next_unanswered(run.term_list_id, run.cursor)

    async def _run(self, run: Run) -> None:
        status = ListStatus.COMPLETED
        try:
            while True:
                if run.stop.is_set():
                    status = ListStatus.CANCELLED
                    break
                if self.closing:
                    status = ListStatus.INTERRUPTED
                    break
                item = await self._next(run)
                if item is None:
                    break
                run.cursor = item.position
                ended = await self._term(run, item)
                if ended is not None:
                    status = ended
                    break
            await self._finish(run.term_list_id, status, "shutdown")
        except Exception as error:  # noqa: BLE001 - the minute check interrupts the list
            log_event(
                logger,
                "term_list.run_failed",
                list_id=run.public_id,
                error_type=type(error).__name__,
            )
        finally:
            self._runs.pop(run.term_list_id, None)
            telemetry.term_lists_running_changed(-1)

    async def _term(self, run: Run, item: TermListItem) -> ListStatus | None:
        """One term through the queue; a status when the list must stop running."""

        position = item.position
        await self._write(
            run.term_list_id,
            position,
            current_position=position,
            item={"error_code": None, "error_message": None},
        )
        started = time.perf_counter()
        try:
            job = await self.jobs.start(
                tenant=run.tenant,
                asker=run.owner,
                query=item.term,
                top=TERM_TOP,
                fresh=False,
                origin=Origin.LIST,
                list_term=ListTerm(run.public_id, run.file_name, position),
            )
        except Exception as error:  # noqa: BLE001 - a refused term is the term's error
            if self.closing or not self.jobs.accepting:
                return ListStatus.INTERRUPTED
            log_event(
                logger,
                "term_list.term_failed",
                list_id=run.public_id,
                error_type=type(error).__name__,
            )
            await self._term_error(run, position, started)
            return None
        run.job = job
        try:
            if run.stop.is_set() and not job.terminal:  # stopped while the term was handed over
                await self.jobs.cancel(self.jobs.view_of(job))
            await job.done.wait()
        finally:
            run.job = None
        elapsed = _ms(time.perf_counter() - started)
        if job.state is JobState.COMPLETED and job.result is not None:
            flow = job.flow or Flow.ANALYST
            await self._write(
                run.term_list_id,
                position,
                current_position=None,
                item={
                    "answer": record_form(job.result),
                    "flow": flow.value,
                    "verdict": job.result.verdict.value,
                    "elapsed_ms": elapsed,
                    "finished_at": self._clock(),
                    "updated_by": run.owner.user_id,
                },
            )
            telemetry.record_term_list_term(flow.value)
            return None
        if job.state is JobState.CANCELLED:
            await self._write(run.term_list_id, None, current_position=None, stop_requested=True)
            return ListStatus.CANCELLED
        if job.state is JobState.INTERRUPTED:
            return ListStatus.INTERRUPTED
        await self._term_error(run, position, started)
        return None

    async def _term_error(self, run: Run, position: int, started: float) -> None:
        """Requirement 18: the term's error is the safe Turkish message; the list goes on."""

        await self._write(
            run.term_list_id,
            position,
            current_position=None,
            item={
                "error_code": TERM_ERROR_CODE,
                "error_message": TERM_ERROR_MESSAGE[:ERROR_MESSAGE_MAX_CHARS],
                "elapsed_ms": _ms(time.perf_counter() - started),
                "finished_at": self._clock(),
            },
        )
        telemetry.record_term_list_term("error")

    async def _finish(self, term_list_id: int, status: ListStatus, reason: str) -> None:
        """The end of a running slice: the status, the slice's time added, no current term."""

        async with self._session_factory() as session:
            repository = TermListRepository(session)
            row = await repository.find_by_id(term_list_id)
            if row is None:  # pragma: no cover - a running list is never deleted
                return
            items = await repository.items(term_list_id)
            await session.commit()
        r = row.record
        now = self._clock()
        elapsed = r.elapsed_before_ms
        if r.run_started_at is not None:
            elapsed += _ms((now - r.run_started_at).total_seconds())
        await self._write(
            term_list_id,
            None,
            status=status.value,
            current_position=None,
            run_started_at=None,
            elapsed_before_ms=elapsed,
            finished_at=now,
        )
        self._ended(r.public_id, status, reason, items, elapsed)

    @staticmethod
    def _ended(
        public_id: str,
        status: ListStatus,
        reason: str,
        items: list[TermListItem],
        elapsed_ms: int,
    ) -> None:
        flows = [i.flow for i in items]
        telemetry.record_term_list_finished(status.value)
        if status is ListStatus.INTERRUPTED:
            log_event(logger, "term_list.interrupted", list_id=public_id, reason=reason)
        log_event(
            logger,
            "term_list.finished",
            list_id=public_id,
            status=status.value,
            analyst=flows.count(Flow.ANALYST.value),
            reused=flows.count(Flow.REUSED.value),
            unavailable=flows.count(Flow.UNAVAILABLE.value),
            errors=sum(1 for i in items if i.error_code is not None),
            duration_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------ stop and resume

    async def cancel(self, tenant_id: int, owner_public_id: str, list_id: str) -> dict[str, Any]:
        """Requirement 8: the running term's model calls are cut and no new call starts; a list
        that does not run is returned as it is."""

        row = await self._owned(tenant_id, owner_public_id, list_id)
        r = row.record
        if r.status != ListStatus.RUNNING.value:
            return await self.snapshot_of(row)
        await self._write(r.term_list_id, None, stop_requested=True)
        log_event(logger, "term_list.stop_requested", list_id=r.public_id)
        run = self._runs.get(r.term_list_id)
        if run is None:  # marked running by no run of this process: the minute check's case
            await self._finish(r.term_list_id, ListStatus.CANCELLED, "")
        else:
            run.stop.set()
            deadline = time.monotonic() + CANCEL_WAIT_SECONDS
            job = run.job
            if job is not None and not job.terminal:
                await self.jobs.cancel(self.jobs.view_of(job))
            if run.task is not None:
                left = max(0.0, deadline - time.monotonic())
                await asyncio.wait({run.task}, timeout=left)
        return await self.snapshot(tenant_id, owner_public_id, list_id)

    async def resume(self, *, tenant: Tenant, owner: Asker, list_id: str) -> dict[str, Any]:
        """Requirement 9: answered terms are kept; unanswered and failed terms are asked again
        in file order; the pause is not counted."""

        row = await self._owned(tenant.tenant_id, owner.public_id, list_id)
        r = row.record
        if r.status == ListStatus.RUNNING.value:
            return await self.snapshot_of(row)
        async with self._session_factory() as session:
            repository = TermListRepository(session)
            running = await repository.running_for_owner(
                tenant.tenant_id, owner.user_id, owner.visitor_id
            )
            left = await repository.unanswered_count(r.term_list_id)
        if running is not None:
            raise _running()
        if not left:
            raise _nothing_to_resume()
        self.jobs.ready()
        self._claimed.add(r.term_list_id)
        try:
            await self._write(
                r.term_list_id,
                None,
                status=ListStatus.RUNNING.value,
                stop_requested=False,
                current_position=None,
                run_started_at=self._clock(),
                finished_at=None,
                updated_by=owner.user_id,
            )
        except IntegrityError:
            self._claimed.discard(r.term_list_id)
            raise _running()
        self._begin(Run(r.term_list_id, r.public_id, r.file_name, tenant, owner))
        log_event(logger, "term_list.resumed", list_id=r.public_id, terms=left)
        return await self.snapshot(tenant.tenant_id, owner.public_id, list_id)

    # ------------------------------------------------------------------ interruption

    async def _interrupt(self, lists: list[TermList], reason: str) -> int:
        now = self._clock()
        for r in lists:
            end = max(r.updated_at, r.run_started_at) if r.run_started_at else now
            elapsed = r.elapsed_before_ms
            if r.run_started_at is not None:
                elapsed += _ms((end - r.run_started_at).total_seconds())
            async with self._session_factory() as session:
                repository = TermListRepository(session)
                await repository.set_list(
                    r.term_list_id,
                    status=ListStatus.INTERRUPTED.value,
                    current_position=None,
                    run_started_at=None,
                    elapsed_before_ms=elapsed,
                    finished_at=now,
                )
                items = await repository.items(r.term_list_id)
                await session.commit()
            self._ended(r.public_id, ListStatus.INTERRUPTED, reason, items, elapsed)
        return len(lists)

    async def interrupt_leftovers(self) -> int:
        """Requirement 10: lists an earlier process left running are interrupted at start."""

        async with self._session_factory() as session:
            leftovers = await TermListRepository(session).running_lists(self.started_at)
        return await self._interrupt(leftovers, "startup")

    async def check(self) -> int:
        """Requirement 10: a list marked running without a run in this process is interrupted."""

        async with self._session_factory() as session:
            running = await TermListRepository(session).running_lists()
        orphans = [
            r
            for r in running
            if r.term_list_id not in self._runs and r.term_list_id not in self._claimed
        ]
        return await self._interrupt(orphans, "check")

    async def run_startup(self, database_ready: Callable[[], Any]) -> None:
        while not await database_ready():
            await asyncio.sleep(1.0)
        try:
            await self.interrupt_leftovers()
        except Exception as error:  # noqa: BLE001 - logged; the minute check tries again
            log_event(logger, "term_list.startup_failed", error_type=type(error).__name__)
        while True:
            await asyncio.sleep(self.check_seconds)
            with contextlib.suppress(Exception):
                await self.check()

    async def shutdown(self, wait_seconds: float = SHUTDOWN_WAIT_SECONDS) -> None:
        """Requirement 10: after the jobs ended as interrupted, every run ends as interrupted."""

        self.closing = True
        runs = list(self._runs.values())
        tasks = [run.task for run in runs if run.task is not None]
        if tasks:
            await asyncio.wait(tasks, timeout=wait_seconds)
        for run in runs:
            if run.task is not None and not run.task.done():
                run.task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await run.task
                with contextlib.suppress(Exception):
                    await self._finish(run.term_list_id, ListStatus.INTERRUPTED, "shutdown")
