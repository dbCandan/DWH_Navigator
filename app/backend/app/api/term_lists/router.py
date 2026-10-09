"""Term list endpoints (data-dictionary/PRDs/005-list-search, API sözleşmesi).

Open to ``kullanici`` and ``yonetici``. A list is its owner's alone: anyone else, a manager
included, gets ``404 term_list_not_found`` (Requirement 14, Decision 8). The upload is the raw
workbook with its name in ``X-Filename`` (dictionary-management Decision 10); the file is read in
memory and never kept. Reports are made per request and downloaded with the session header.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.api.excel_transfer import (
    EXCEL_REQUEST_BODY,
    EXCEL_RESPONSE,
    excel_download,
    read_excel_upload,
)
from app.core import telemetry
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.db.session import get_db
from app.domain.accounts import ROLE_USER
from app.domain.term_lists import Rejection
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.analysis.jobs import AnalysisAnswer
from app.schemas.errors import error_responses
from app.schemas.term_lists.lists import TermListPage, TermListSnapshot
from app.services.analysis.jobs import Asker, Tenant
from app.services.request_scope import acting_user_with_role, active_tenant
from app.services.term_lists import TermLists

logger = logging.getLogger("app.lists")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

_NOT_FOUND = {404: "term_list_not_found: liste yok ya da başkasının"}
_NOT_ANSWERED = {
    404: "term_list_not_found: liste yok ya da başkasının; term_list_item_not_answered: terimin "
    "cevabı yok"
}

router = APIRouter(
    prefix="/term-lists",
    tags=["term-lists"],
    dependencies=[Depends(require_role(ROLE_USER))],
    responses=error_responses(
        {
            401: "not_authenticated: oturum yok",
            403: "forbidden: rol yok; cross_site_request: istek başka bir siteden geldi",
        }
    ),
)

Session = Annotated[AsyncSession, Depends(get_db)]


def get_term_lists(request: Request) -> TermLists:
    lists: TermLists = request.app.state.term_lists
    return lists


Lists = Annotated[TermLists, Depends(get_term_lists)]


async def _caller(session: AsyncSession, context: CurrentContext) -> tuple[Tenant, Asker]:
    users = UserRepository(session)
    actor = await acting_user_with_role(users, context, ROLE_USER)
    tenant = await active_tenant(users, context)
    await session.commit()  # the request's session holds no transaction while a list is read
    return Tenant(tenant.tenant_id, tenant.public_id), Asker(
        actor.user_id, actor.public_id, actor.display_name
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TermListSnapshot,
    openapi_extra=EXCEL_REQUEST_BODY,
    responses=error_responses(
        {
            409: "term_list_running: kurumda çalışan bir liste var",
            413: "upload_too_large: gövde 20 MB'tan büyük",
            415: "unsupported_media_type: gövde Excel değil",
            422: ", ".join(code.value for code in Rejection),
            503: "search_index_not_ready, analysis_unavailable",
        }
    ),
)
async def upload_list(
    request: Request, context: CurrentContext, session: Session, lists: Lists
) -> dict[str, Any]:
    """Read a one-column list, keep it with its terms and start answering them one by one."""

    tenant, owner = await _caller(session, context)
    try:
        upload = await read_excel_upload(
            request, empty_code=Rejection.NOT_XLSX.value, default_name="liste.xlsx"
        )
    except ApplicationError as refused:
        telemetry.record_term_list_upload_rejected(refused.code)
        log_event(logger, "term_list.upload_rejected", code=refused.code)
        raise
    return await lists.start(
        tenant=tenant, owner=owner, file_name=upload.filename, data=upload.data
    )


@router.get("", response_model=TermListPage)
async def list_lists(
    context: CurrentContext,
    session: Session,
    lists: Lists,
    page: Annotated[int, Query(ge=1, le=10_000_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """The caller's kept lists, newest first."""

    tenant, owner = await _caller(session, context)
    return await lists.page(tenant.tenant_id, owner.user_id, page, page_size)


@router.get("/{list_id}", response_model=TermListSnapshot, responses=error_responses(_NOT_FOUND))
async def read_list(
    list_id: str, context: CurrentContext, session: Session, lists: Lists
) -> dict[str, Any]:
    """The list's progress, a row per term."""

    tenant, owner = await _caller(session, context)
    return await lists.snapshot(tenant.tenant_id, owner.public_id, list_id)


@router.get(
    "/{list_id}/items/{position}",
    response_model=AnalysisAnswer,
    response_model_by_alias=True,
    responses=error_responses(_NOT_ANSWERED),
)
async def read_term(
    list_id: str, position: int, context: CurrentContext, session: Session, lists: Lists
) -> dict[str, Any]:
    """An answered term's full answer, the votes applied for the caller."""

    tenant, owner = await _caller(session, context)
    return await lists.item(tenant.tenant_id, owner.public_id, list_id, position)


@router.get(
    "/{list_id}/items/{position}/report",
    response_class=Response,
    responses={200: EXCEL_RESPONSE, **error_responses(_NOT_ANSWERED)},
)
async def term_report(
    list_id: str, position: int, context: CurrentContext, session: Session, lists: Lists
) -> Response:
    """The term's single-question Excel report, made from its kept answer."""

    tenant, owner = await _caller(session, context)
    name, data = await lists.item_report(tenant.tenant_id, owner.public_id, list_id, position)
    return excel_download(name, data)


@router.get(
    "/{list_id}/report",
    response_class=Response,
    responses={200: EXCEL_RESPONSE, **error_responses(_NOT_FOUND)},
)
async def list_report(
    list_id: str, context: CurrentContext, session: Session, lists: Lists
) -> Response:
    """The whole list in one workbook (also while it runs)."""

    tenant, owner = await _caller(session, context)
    name, data = await lists.report(tenant.tenant_id, owner.public_id, list_id)
    return excel_download(name, data)


@router.post(
    "/{list_id}/cancel", response_model=TermListSnapshot, responses=error_responses(_NOT_FOUND)
)
async def cancel_list(
    list_id: str, context: CurrentContext, session: Session, lists: Lists
) -> dict[str, Any]:
    """Stop the list; a list that does not run is returned as it is."""

    tenant, owner = await _caller(session, context)
    return await lists.cancel(tenant.tenant_id, owner.public_id, list_id)


@router.post(
    "/{list_id}/resume",
    response_model=TermListSnapshot,
    responses=error_responses(
        {
            **_NOT_FOUND,
            409: "term_list_running: kurumda çalışan bir liste var; term_list_nothing_to_resume: "
            "devam edecek terim yok",
            503: "search_index_not_ready, analysis_unavailable",
        }
    ),
)
async def resume_list(
    list_id: str, context: CurrentContext, session: Session, lists: Lists
) -> dict[str, Any]:
    """Go on from where the list stopped; a running list is returned as it is."""

    tenant, owner = await _caller(session, context)
    return await lists.resume(tenant=tenant, owner=owner, list_id=list_id)
