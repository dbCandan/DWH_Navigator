"""LLM call log endpoints of the administration screen.

Every endpoint needs a session and the ``yonetici`` role, re-read from the database, because the
rows hold prompts and replies. The search text never reaches a log: the request log keeps only the
route template.
"""

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
from app.schemas.llm.call_logs import LlmCallLogDetail, LlmCallLogPage, LlmCallLogRow
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


def _invalid_filter() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_filter", "Süzgeç değerleri geçersiz."
    )


async def _tenant_id(session: AsyncSession, context: CurrentContext) -> int:
    users = UserRepository(session)
    await acting_user_with_role(users, context, ROLE_MANAGER)
    return (await active_tenant(users, context)).tenant_id


@router.get(
    "",
    response_model=LlmCallLogPage,
    responses=error_responses({422: "invalid_filter: amaç, sonuç, metin ya da sayı geçersiz"}),
)
async def list_calls(
    context: CurrentContext,
    session: Session,
    settings: Annotated[Settings, Depends(get_settings)],
    purpose: Annotated[str | None, Query(description="Çağrının amacı")] = None,
    outcome: Annotated[str | None, Query(description="Çağrının sonucu")] = None,
    q: Annotated[str | None, Query(description="İstek ve yanıtta aranan metin")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> LlmCallLogPage:
    """The newest calls without their bodies, and how many match the filters."""

    if purpose is not None and purpose not in {item.value for item in LlmPurpose}:
        raise _invalid_filter()
    if outcome is not None and outcome not in {item.value for item in LlmOutcome}:
        raise _invalid_filter()
    if q is not None and len(q) > MAX_TEXT:
        raise _invalid_filter()
    tenant_id = await _tenant_id(session, context)
    filters = CallLogFilters(purpose=purpose, outcome=outcome, q=(q or "").strip() or None)
    rows, total = await LlmCallLogRepository(session).page(tenant_id, filters, limit)
    return LlmCallLogPage(
        rows=[LlmCallLogRow.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        retention_days=settings.llm_call_log_days,
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
