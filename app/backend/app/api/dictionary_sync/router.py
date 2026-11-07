"""HTTP boundary of the dictionary update (011-dictionary-sync plan.md)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.api.search_index_dependency import get_search_index
from app.db.session import get_db
from app.domain.accounts import ROLE_MANAGER
from app.schemas.dictionary.sync import (
    ApplySuggestions,
    ChangesPage,
    RunDetail,
    RunsPage,
    RunSummary,
    Source,
    SourceInput,
    SourceTest,
    VersionsPage,
)
from app.schemas.errors import error_responses
from app.services.dictionary_sync_service import DictionarySyncService
from app.services.search_index import SearchIndex

router = APIRouter(
    prefix="/dictionary",
    tags=["dictionary"],
    dependencies=[Depends(require_role(ROLE_MANAGER))],
    responses=error_responses(
        {
            401: "not_authenticated: oturum yok",
            403: "forbidden: yonetici değil; cross_site_request: istek başka bir siteden geldi",
        }
    ),
)


def get_sync_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    index: Annotated[SearchIndex, Depends(get_search_index)],
) -> DictionarySyncService:
    return DictionarySyncService(session, request.app.state.dictionary_sync, index)


Service = Annotated[DictionarySyncService, Depends(get_sync_service)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]


@router.get("/source", response_model=Source)
async def read_source(context: CurrentContext, service: Service) -> Source:
    return await service.source(context)


@router.put("/source", response_model=Source)
async def save_source(context: CurrentContext, service: Service, body: SourceInput) -> Source:
    return await service.save_source(context, body)


@router.post("/source/test", response_model=SourceTest)
async def test_source(context: CurrentContext, service: Service, body: SourceInput) -> SourceTest:
    return await service.test_source(context, body)


@router.post("/sync", response_model=RunSummary, status_code=status.HTTP_202_ACCEPTED)
async def start_sync(context: CurrentContext, service: Service) -> RunSummary:
    return await service.start(context)


@router.get("/sync/runs", response_model=RunsPage)
async def list_runs(
    context: CurrentContext, service: Service, page: Page = 1, page_size: PageSize = 20
) -> RunsPage:
    return await service.list_runs(context, page, page_size)


@router.get("/sync/runs/{run_id}", response_model=RunDetail)
async def read_run(context: CurrentContext, service: Service, run_id: str) -> RunDetail:
    return await service.run(context, run_id)


@router.get("/sync/runs/{run_id}/changes", response_model=ChangesPage)
async def read_changes(
    context: CurrentContext,
    service: Service,
    run_id: str,
    kind: str = "",
    search: Annotated[str, Query(max_length=200)] = "",
    page: Page = 1,
    page_size: PageSize = 50,
) -> ChangesPage:
    return await service.changes(context, run_id, kind, search, page, page_size)


@router.post("/sync/runs/{run_id}/approve", response_model=RunDetail)
async def approve_run(context: CurrentContext, service: Service, run_id: str) -> RunDetail:
    return await service.approve(context, run_id)


@router.post("/sync/runs/{run_id}/reject", response_model=RunDetail)
async def reject_run(context: CurrentContext, service: Service, run_id: str) -> RunDetail:
    return await service.reject(context, run_id)


@router.post("/sync/runs/{run_id}/suggestions/apply", response_model=RunDetail)
async def apply_suggestions(
    context: CurrentContext, service: Service, run_id: str, body: ApplySuggestions
) -> RunDetail:
    return await service.apply_suggestions(context, run_id, body)


@router.get("/versions", response_model=VersionsPage)
async def list_versions(context: CurrentContext, service: Service) -> VersionsPage:
    return await service.versions(context)


@router.post(
    "/versions/{version_id}/restore",
    response_model=RunSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def restore_version(context: CurrentContext, service: Service, version_id: str) -> RunSummary:
    return await service.restore(context, version_id)
