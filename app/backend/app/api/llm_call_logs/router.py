"""LLM call log endpoints of the administration screen.

Every endpoint needs a session and the ``yonetici`` role, re-read from the database, because the
rows hold prompts and replies. Deleting removes the rows for good; it is logged with the count and
the person, never with the filter text. The search text never reaches a log: the request log keeps only the
route template.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError
from app.db.session import get_db
from app.domain.accounts import ROLE_MANAGER
from app.domain.llm import LlmOutcome, LlmPurpose
from app.infrastructure.repositories.llm_call_log_repository import (
    CallLogFilters,
    LlmCallLogRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.errors import error_responses
from app.schemas.llm.call_logs import (
    LlmCallLogDetail,
    LlmCallLogPage,
    LlmCallLogRow,
    LlmCallLogsDeleted,
)
from app.services.llm_call_log import delete_calls
from app.services.request_scope import acting_user_with_role, active_tenant

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_TEXT = 200

router = APIRouter(
    prefix="/llm-call-logs",
    tags=["llm-call-logs"],
    dependencies=[Depends(require_role(ROLE_MANAGER))],
    responses=error_responses(
        {
            401: "not_authenticated: oturum yok",
            403: "forbidden: yonetici değil; cross_site_request: istek başka bir siteden geldi",
        }
    ),
)
Session = Annotated[AsyncSession, Depends(get_db)]


def _is_public_id(value: str) -> bool:
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


def _invalid_filter() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_filter", "Süzgeç değerleri geçersiz."
    )


async def _tenant_id(session: AsyncSession, context: CurrentContext) -> int:
    users = UserRepository(session)
    await acting_user_with_role(users, context, ROLE_MANAGER)
    return (await active_tenant(users, context)).tenant_id


def _filters(
    purpose: str | None, outcome: str | None, q: str | None, analysis: str | None
) -> CallLogFilters:
    if purpose is not None and purpose not in {item.value for item in LlmPurpose}:
        raise _invalid_filter()
    if outcome is not None and outcome not in {item.value for item in LlmOutcome}:
        raise _invalid_filter()
    if q is not None and len(q) > MAX_TEXT:
        raise _invalid_filter()
    if analysis is not None and not _is_public_id(analysis):
        raise _invalid_filter()
    return CallLogFilters(
        purpose=purpose or None,
        outcome=outcome or None,
        q=(q or "").strip() or None,
        analysis=analysis or None,
    )


def _until(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        raise _invalid_filter() from None
    if value.tzinfo is None:
        raise _invalid_filter()
    return value.astimezone(UTC)


Purpose = Annotated[str | None, Query(description="Çağrının amacı")]
Outcome = Annotated[str | None, Query(description="Çağrının sonucu")]
Text = Annotated[str | None, Query(description="İstek ve yanıtta aranan metin")]
Analysis = Annotated[
    str | None, Query(description="Yalnız bu analizin çağrıları (analizin public_id'si)")
]


@router.get(
    "",
    response_model=LlmCallLogPage,
    responses=error_responses(
        {422: "invalid_filter: amaç, sonuç, metin, analiz ya da sayı geçersiz"}
    ),
)
async def list_calls(
    context: CurrentContext,
    session: Session,
    settings: Annotated[Settings, Depends(get_settings)],
    purpose: Purpose = None,
    outcome: Outcome = None,
    q: Text = None,
    analysis: Analysis = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> LlmCallLogPage:
    """The newest calls without their bodies, and how many match the filters."""

    filters = _filters(purpose, outcome, q, analysis)
    tenant_id = await _tenant_id(session, context)
    until = datetime.now(UTC)
    rows, total = await LlmCallLogRepository(session).page(tenant_id, filters, limit)
    return LlmCallLogPage(
        rows=[LlmCallLogRow.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        retention_days=settings.llm_call_log_days,
        until=until,
    )


@router.delete(
    "",
    response_model=LlmCallLogsDeleted,
    responses=error_responses(
        {
            422: (
                "llm_call_log_delete_scope_missing: until ya da süzgeç veya all=true yok; "
                "invalid_filter: amaç, sonuç, metin, analiz ya da zaman geçersiz"
            )
        }
    ),
)
async def delete_logs(
    context: CurrentContext,
    session: Session,
    until: Annotated[
        str | None, Query(description="ISO 8601, saat dilimli; bundan sonra gelen çağrılar kalır")
    ] = None,
    purpose: Purpose = None,
    outcome: Outcome = None,
    q: Text = None,
    analysis: Analysis = None,
    all: Annotated[str | None, Query(description="true: until'den önceki bütün çağrılar")] = None,
) -> dict[str, int]:
    """Delete for good the tenant's calls that match the filters, or all of them with all=true."""

    users = UserRepository(session)
    actor = await acting_user_with_role(users, context, ROLE_MANAGER)
    if all is not None and all not in ("true", "false"):
        raise _invalid_filter()
    filters = _filters(purpose, outcome, q, analysis)
    everything = all == "true"
    given = any((filters.purpose, filters.outcome, filters.q, filters.analysis))
    if until is None or not (everything or given):
        raise ApplicationError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "llm_call_log_delete_scope_missing",
            "Silinecek kayıt seçilmedi.",
        )
    at = _until(until)
    tenant_id = (await active_tenant(users, context)).tenant_id
    return await delete_calls(
        session, tenant_id, filters, at, everything=everything, actor_public_id=actor.public_id
    )


@router.get(
    "/{public_id}",
    response_model=LlmCallLogDetail,
    responses=error_responses({404: "llm_call_log_not_found: kayıt yok ya da süresi dolmuş"}),
)
async def read_call(public_id: UUID, context: CurrentContext, session: Session) -> LlmCallLogDetail:
    """One call with the request and response bodies of each HTTP request."""

    tenant_id = await _tenant_id(session, context)
    row = await LlmCallLogRepository(session).get(tenant_id, str(public_id))
    if row is None:
        raise ApplicationError(
            status.HTTP_404_NOT_FOUND, "llm_call_log_not_found", "Kayıt bulunamadı."
        )
    return LlmCallLogDetail.model_validate(row, from_attributes=True)
