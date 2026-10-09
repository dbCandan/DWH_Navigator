"""Analysis record endpoints of the administration screen (data-dictionary/PRDs/
008-analysis-records, API sözleşmesi).

Every endpoint needs a session and the ``yonetici`` role; the deletion re-reads the account.
Filter values are checked by type and range and refused with ``422 invalid_filter``; the text
filter never reaches a log (the request log keeps only the route template).
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.core.errors import ApplicationError
from app.db.session import get_db
from app.domain.accounts import ROLE_MANAGER
from app.domain.analysis_records import Flow
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.analysis_records.records import (
    Askers,
    DailyCounts,
    RecordDetail,
    RecordPage,
    RecordsDeleted,
    RecordSummary,
)
from app.schemas.errors import error_responses
from app.services.analysis_records import PERIODS, AnalysisRecordsService, Filters
from app.services.request_scope import acting_user_with_role, active_tenant

MAX_TEXT = 200
MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 150
MAX_DAYS = 31
DEFAULT_DAYS = 14

_INVALID = {422: "invalid_filter: dönem, akış, soran, metin, zaman ya da sayfa geçersiz"}

router = APIRouter(
    prefix="/analysis-records",
    tags=["analysis-records"],
    dependencies=[Depends(require_role(ROLE_MANAGER))],
    responses=error_responses(
        {
            401: "not_authenticated: oturum yok",
            403: "forbidden: yonetici değil; cross_site_request: istek başka bir siteden geldi",
        }
    ),
)
Session = Annotated[AsyncSession, Depends(get_db)]


def invalid_filter() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_filter", "Süzgeç değerleri geçersiz."
    )


def _until(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(UTC)
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        raise invalid_filter() from None
    if value.tzinfo is None:
        raise invalid_filter()
    return value.astimezone(UTC)


def _number(raw: str | None, default: int, low: int, high: int) -> int:
    if raw is None:
        return default
    if not raw.isdigit() or not low <= int(raw) <= high:
        raise invalid_filter()
    return int(raw)


def _filters(period: str | None, flow: str | None, asked_by: str | None, q: str | None) -> Filters:
    if period is not None and period not in PERIODS:
        raise invalid_filter()
    if flow is not None and flow not in {f.value for f in Flow}:
        raise invalid_filter()
    if asked_by is not None:
        try:
            asked_by = str(UUID(asked_by))
        except ValueError:
            raise invalid_filter() from None
    if q is not None:
        if len(q) > MAX_TEXT:
            raise invalid_filter()
        q = q.strip() or None
    return Filters(period=period, flow=flow, asked_by=asked_by, q=q)


Period = Annotated[str | None, Query(description="today, 7d (varsayılan), 30d ya da all")]
FlowQ = Annotated[str | None, Query(description="Altı akıştan biri")]
AskedBy = Annotated[str | None, Query(description="Soranın public_id değeri")]
Text = Annotated[str | None, Query(description="En çok 200 karakterlik metin")]
Until = Annotated[str | None, Query(description="ISO 8601, saat dilimli")]


async def _tenant_id(session: AsyncSession, context: CurrentContext) -> int:
    return (await active_tenant(UserRepository(session), context)).tenant_id


@router.get("", response_model=RecordPage, responses=error_responses(_INVALID))
async def list_records(
    context: CurrentContext,
    session: Session,
    period: Period = None,
    flow: FlowQ = None,
    asked_by: AskedBy = None,
    q: Text = None,
    until: Until = None,
    page: Annotated[str | None, Query()] = None,
    page_size: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Finished records, newest first, a page at a time."""

    filters = _filters(period, flow, asked_by, q)
    at = _until(until)
    number = _number(page, 1, 1, 10_000_000)
    size = _number(page_size, DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
    tenant_id = await _tenant_id(session, context)
    return await AnalysisRecordsService(session).page(tenant_id, filters, at, number, size)


@router.get("/summary", response_model=RecordSummary, responses=error_responses(_INVALID))
async def records_summary(
    context: CurrentContext,
    session: Session,
    period: Period = None,
    flow: FlowQ = None,
    asked_by: AskedBy = None,
    q: Text = None,
    until: Until = None,
) -> dict[str, Any]:
    """Counts, durations, phases, model use and askers of the matching records."""

    filters = _filters(period, flow, asked_by, q)
    at = _until(until)
    tenant_id = await _tenant_id(session, context)
    return await AnalysisRecordsService(session).summary(tenant_id, filters, at)


@router.get("/daily-counts", response_model=DailyCounts, responses=error_responses(_INVALID))
async def daily_counts(
    context: CurrentContext,
    session: Session,
    days: Annotated[str | None, Query(description="1-31, varsayılan 14")] = None,
) -> dict[str, Any]:
    """Records with and without suggested tables per Istanbul calendar day."""

    count = _number(days, DEFAULT_DAYS, 1, MAX_DAYS)
    tenant_id = await _tenant_id(session, context)
    return await AnalysisRecordsService(session).daily_counts(tenant_id, count, datetime.now(UTC))


@router.get("/askers", response_model=Askers)
async def askers(context: CurrentContext, session: Session) -> dict[str, Any]:
    """Everyone with a finished record, by display name."""

    tenant_id = await _tenant_id(session, context)
    return await AnalysisRecordsService(session).askers(tenant_id)


@router.get(
    "/{public_id}",
    response_model=RecordDetail,
    responses=error_responses({404: "analysis_record_not_found: yok, sürüyor ya da silinmiş"}),
)
async def record_detail(
    public_id: str, context: CurrentContext, session: Session
) -> dict[str, Any]:
    """One finished record with its phases and every step; never the full answer."""

    tenant_id = await _tenant_id(session, context)
    detail = await AnalysisRecordsService(session).detail(tenant_id, public_id)
    if detail is None:
        raise ApplicationError(
            status.HTTP_404_NOT_FOUND, "analysis_record_not_found", "Kayıt bulunamadı."
        )
    return detail


@router.delete(
    "",
    response_model=RecordsDeleted,
    responses=error_responses(
        {422: "analysis_delete_scope_missing: süzgeç ya da all=true yok; invalid_filter"}
    ),
)
async def delete_records(
    context: CurrentContext,
    session: Session,
    until: Until = None,
    period: Period = None,
    flow: FlowQ = None,
    asked_by: AskedBy = None,
    q: Text = None,
    all: Annotated[str | None, Query(description="true: until'den önceki bütün kayıtlar")] = None,
) -> dict[str, int]:
    """Delete the matching finished records for good; ``until`` is required."""

    actor = await acting_user_with_role(UserRepository(session), context, ROLE_MANAGER)
    if all is not None and all not in ("true", "false"):
        raise invalid_filter()
    filters = _filters(period, flow, asked_by, q)
    everything = all == "true"
    if until is None or not (everything or filters.any_given):
        raise ApplicationError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "analysis_delete_scope_missing",
            "Silinecek analiz seçilmedi",
        )
    at = _until(until)
    tenant_id = await _tenant_id(session, context)
    return await AnalysisRecordsService(session).delete(
        tenant_id, filters, at, everything=everything, actor_public_id=actor.public_id
    )
