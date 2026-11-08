"""Question analysis endpoints (data-dictionary/PRDs/004-question-analysis, API sözleşmesi).

Starting, reading, following, stopping and reporting an analysis job and the status take no
session: the visitor of the ``X-Device-Id`` header asks (application-foundation
003-anonymous-visitor Requirement 3). Only the job's owner reaches a job, anyone else gets
``404 analysis_not_found``. The saved-answer summary and deletion are for ``yonetici``. The live
stream checks the device id and the owner before its first byte; nothing is in the address.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.api.excel_transfer import EXCEL_RESPONSE, excel_download
from app.api.search_index_dependency import get_search_index
from app.api.visitor.dependencies import CurrentVisitor, visitor_asker
from app.core import telemetry
from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.db.session import get_db
from app.domain.accounts import ROLE_MANAGER
from app.domain.analysis_records import QUERY_MAX_CHARS, JobState
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.analysis.jobs import (
    ActiveAnalysis,
    AnalysisJob,
    AnalysisJobWithResult,
    AnalysisStart,
    AnalysisStreamEvent,
    ModelStateOut,
    SavedAnswersRemoved,
    SavedAnswerSummaryOut,
    StatusOut,
)
from app.schemas.errors import error_responses
from app.services.analysis.jobs import AnalysisJobs, JobView, Tenant
from app.services.analysis.llm.port import ModelSampling
from app.services.analysis.model_view import sampling_of
from app.services.analysis.pipeline import ISTANBUL, Engine
from app.services.analysis.report.excel import report_filename, write_ask_report
from app.services.request_scope import acting_user_with_role, active_tenant
from app.services.search_index import SearchIndex
from app.services.search_settings_schema import defaults
from app.services.visitors import VisitorIdentity

logger = logging.getLogger("app.analysis")

MAX_BODY_BYTES = 32 * 1024
DEFAULT_TOP = 5
_ALLOWED_CONTROLS = frozenset("\t\n\r")

_ERROR_TEXTS = {
    400: "device_id_required: X-Device-Id eksik ya da UUID 4 değil",
    403: "tenant_forbidden: başka kiracı; cross_site_request: istek başka bir siteden geldi",
    429: "rate_limited: yeni ziyaretçi sınırı",
}
_MANAGER_ERRORS = error_responses(
    {
        401: "not_authenticated: oturum yok",
        403: "forbidden: yonetici değil; cross_site_request: istek başka bir siteden geldi",
    }
)
_ERRORS = error_responses(_ERROR_TEXTS)
_NOT_FOUND = {404: "analysis_not_found: analiz yok ya da başkasının"}


def _json_errors(described: dict[int, str]) -> dict[int | str, dict[str, Any]]:
    """Error envelopes of the stream endpoint: JSON, refused before the stream opens."""

    schema = {"$ref": "#/components/schemas/ErrorResponse"}
    return {
        code: {"description": text, "content": {"application/json": {"schema": schema}}}
        for code, text in described.items()
    }


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


router = APIRouter(tags=["analyses"])
_manager = [Depends(require_role(ROLE_MANAGER))]


def get_analysis_jobs(request: Request) -> AnalysisJobs:
    jobs: AnalysisJobs = request.app.state.analysis_jobs
    return jobs


Jobs = Annotated[AnalysisJobs, Depends(get_analysis_jobs)]
Session = Annotated[AsyncSession, Depends(get_db)]
Index = Annotated[SearchIndex, Depends(get_search_index)]


async def _tenant(session: AsyncSession, context: CurrentContext) -> Tenant:
    tenant = await active_tenant(UserRepository(session), context)
    return Tenant(tenant.tenant_id, tenant.public_id)


def _visitor_tenant(visitor: VisitorIdentity) -> Tenant:
    return Tenant(visitor.tenant_id, visitor.tenant_public_id)


async def _own(jobs: AnalysisJobs, visitor: VisitorIdentity, analysis_id: str) -> JobView:
    return await jobs.find(visitor.tenant_id, visitor.public_id, analysis_id)


def _invalid(code: str, message: str) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, code, message)


def checked_query(raw: str) -> str:
    """Requirement 4: trimmed, not empty, at most 4000 characters, no control character other
    than tab, line feed and carriage return."""

    query = raw.strip()
    if not query:
        raise _invalid("query_empty", "Talep metni boş")
    if len(query) > QUERY_MAX_CHARS:
        raise _invalid("query_too_long", "Talep çok uzun (en fazla 4000 karakter)")
    if any((ord(c) < 0x20 or ord(c) == 0x7F) and c not in _ALLOWED_CONTROLS for c in query):
        raise _invalid(
            "query_invalid_characters", "Talep metninde izin verilmeyen bir karakter var."
        )
    return query


async def _start_body(request: Request) -> AnalysisStart:
    declared = request.headers.get("content-length", "")
    too_large = ApplicationError(
        status.HTTP_413_CONTENT_TOO_LARGE, "request_too_large", "İstek gövdesi çok büyük."
    )
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise too_large
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise too_large
    try:
        return AnalysisStart.model_validate_json(bytes(body))
    except ValidationError:
        raise _invalid("invalid_request", "İstek değerleri geçersiz.") from None


def _envelope(view: JobView) -> AnalysisJob:
    return AnalysisJob.model_validate(view.envelope())


@router.post(
    "/analyses",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AnalysisJob,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": AnalysisStart.model_json_schema(
                        ref_template="#/components/schemas/{model}"
                    )
                }
            },
        }
    },
    responses=error_responses(
        {
            413: "request_too_large: gövde 32 KB'tan büyük",
            422: "query_empty, query_too_long, query_invalid_characters, invalid_request",
            400: _ERROR_TEXTS[400],
            403: _ERROR_TEXTS[403],
            429: "rate_limited: ziyaretçi başına 60 saniyede 30, adres başına 120'den çok istek",
            503: "analysis_queue_full, analysis_unavailable, search_index_not_ready",
        }
    ),
)
async def start_analysis(
    request: Request,
    response: Response,
    visitor: CurrentVisitor,
    jobs: Jobs,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisJob:
    """Accept a question; a saved answer completes the job at once, otherwise it is queued."""

    jobs.check_rate(visitor.public_id, visitor.address)
    body = await _start_body(request)
    query = checked_query(body.query)
    job = await jobs.start(
        tenant=_visitor_tenant(visitor),
        asker=visitor_asker(visitor),
        query=query,
        top=body.top,
        fresh=body.fresh,
    )
    response.headers["Location"] = f"{settings.api_prefix}/analyses/{job.public_id}"
    return _envelope(jobs.view_of(job))


@router.get("/analyses/active", response_model=ActiveAnalysis, responses=_ERRORS)
async def active_analysis(visitor: CurrentVisitor, jobs: Jobs) -> ActiveAnalysis:
    """The visitor's most recently started single question that is queued or running."""

    job = jobs.active(visitor.public_id)
    return ActiveAnalysis(analysis=_envelope(jobs.view_of(job)) if job is not None else None)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisJobWithResult,
    response_model_by_alias=True,
    responses=error_responses({**_ERROR_TEXTS, **_NOT_FOUND}),
)
async def read_analysis(analysis_id: str, visitor: CurrentVisitor, jobs: Jobs) -> dict[str, Any]:
    """The job; a completed job carries its answer with the visitor's votes applied."""

    view = await _own(jobs, visitor, analysis_id)
    out: dict[str, Any] = view.envelope()
    if view.state is JobState.COMPLETED and view.result is not None:
        out["result"] = await jobs.answer(visitor.tenant_id, visitor.public_id, view)
    return out


@router.get(
    "/analyses/{analysis_id}/events",
    response_class=EventStreamResponse,
    responses={
        200: {
            "model": AnalysisStreamEvent,
            "description": (
                "text/event-stream: every event is an id: line and one data: line with this JSON; "
                "': canlı' comment lines keep the connection alive every 15 seconds."
            ),
        },
        **_json_errors(
            {
                **_ERROR_TEXTS,
                **_NOT_FOUND,
                429: "too_many_streams: ziyaretçi başına 5 akış; rate_limited",
            }
        ),
    },
)
async def follow_analysis(
    analysis_id: str,
    visitor: CurrentVisitor,
    jobs: Jobs,
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventStreamResponse:
    """Live progress: a snapshot, the missed step events after ``Last-Event-ID``, then live;
    the stream ends at the terminal event or when the client leaves."""

    view = await _own(jobs, visitor, analysis_id)
    user = visitor.public_id
    jobs.open_stream(user)
    last = int(last_event_id) if last_event_id is not None and last_event_id.isdigit() else None

    async def stream() -> Any:
        try:
            async for chunk in jobs.events(view, last_event_id=last, expires_at=None):
                yield chunk
        finally:
            jobs.close_stream(user)

    return EventStreamResponse(
        stream(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/analyses/{analysis_id}/cancel",
    response_model=AnalysisJob,
    responses=error_responses({**_ERROR_TEXTS, **_NOT_FOUND}),
)
async def cancel_analysis(analysis_id: str, visitor: CurrentVisitor, jobs: Jobs) -> AnalysisJob:
    """Stop the job; a finished job is returned as it is."""

    view = await _own(jobs, visitor, analysis_id)
    return _envelope(await jobs.cancel(view))


@router.get(
    "/analyses/{analysis_id}/report",
    response_class=Response,
    responses={
        200: EXCEL_RESPONSE,
        **error_responses(
            {
                **_ERROR_TEXTS,
                **_NOT_FOUND,
                409: "analysis_has_no_result: tamamlanmamış analiz",
            }
        ),
    },
)
async def analysis_report(analysis_id: str, visitor: CurrentVisitor, jobs: Jobs) -> Response:
    """The single-question Excel report, made in memory from the record's answer."""

    view = await _own(jobs, visitor, analysis_id)
    if view.state is not JobState.COMPLETED or view.result is None:
        raise ApplicationError(
            status.HTTP_409_CONFLICT, "analysis_has_no_result", "Bu analizin raporu yok."
        )
    started = time.perf_counter()
    try:
        data = await asyncio.to_thread(write_ask_report, view.result)
    except Exception:
        telemetry.record_analysis_report("error")
        raise
    telemetry.record_analysis_report("ok")
    name = report_filename("ask", view.result.query, datetime.now(ISTANBUL))
    log_event(
        logger,
        "analysis.report_generated",
        analysis_id=view.public_id,
        duration_ms=round((time.perf_counter() - started) * 1000),
        size_bytes=len(data),
    )
    return excel_download(name, data)


@router.get("/status", response_model=StatusOut, responses=_ERRORS)
async def analysis_status(visitor: CurrentVisitor, jobs: Jobs, index: Index) -> StatusOut:
    """Requirement 17: the serving dictionary, the chat model and its state, the shortlist."""

    tenant = _visitor_tenant(visitor)
    serving = index.serving
    engine = serving.engine if serving is not None else None
    state = await jobs.models.model_state(
        tenant_id=tenant.tenant_id, tenant_public_id=tenant.public_id
    )
    values = serving.settings_values if serving is not None else defaults()
    return StatusOut(
        columns=len(engine.dictionary.columns) if engine else 0,
        objects=len(engine.objects) if engine else 0,
        dictionary_version=engine.dictionary.version if engine else "",
        llm=state.model if state.state != "none" else "",
        llm_state=ModelStateOut(
            state=state.state,
            model=state.model,
            code=state.code.value if state.code is not None else None,
            reason=state.reason,
        ),
        shortlist=int(values["analyst.shortlist"]),
    )


@router.get(
    "/saved-answers/summary",
    response_model=SavedAnswerSummaryOut,
    dependencies=_manager,
    responses=_MANAGER_ERRORS,
)
async def saved_answers_summary(
    context: CurrentContext, session: Session, jobs: Jobs, index: Index
) -> SavedAnswerSummaryOut:
    """Requirement 15: every saved answer, those the current engine and model can use (top 5),
    and the newest one's time."""

    tenant = await _tenant(session, context)
    await session.commit()
    fingerprint_of: Callable[[str], str] | None = None
    if index.serving is not None:
        connection = await jobs.models.snapshot(
            tenant_id=tenant.tenant_id, tenant_public_id=tenant.public_id
        )
        engine, sampling = index.serving.engine, sampling_of(connection)
        fingerprint_of = partial(_fingerprint, engine, sampling)
    summary = await jobs.saved_answers.summary(tenant.tenant_id, fingerprint_of)
    return SavedAnswerSummaryOut(
        total=summary.total, usable=summary.usable, newest_at=summary.newest_at
    )


def _fingerprint(engine: Engine, sampling: ModelSampling, query: str) -> str:
    return engine.cache_fingerprint(query, DEFAULT_TOP, sampling)


@router.delete(
    "/saved-answers",
    response_model=SavedAnswersRemoved,
    dependencies=_manager,
    responses=_MANAGER_ERRORS,
)
async def clear_saved_answers(
    context: CurrentContext, session: Session, jobs: Jobs
) -> SavedAnswersRemoved:
    """Delete every saved answer of the tenant for good; a repeat removes 0."""

    actor = await acting_user_with_role(UserRepository(session), context, ROLE_MANAGER)
    tenant = await _tenant(session, context)
    await session.commit()
    return SavedAnswersRemoved(
        removed=await jobs.saved_answers.clear(tenant.tenant_id, actor.public_id)
    )
