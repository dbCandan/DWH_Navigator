"""Search settings and search index endpoints (data-dictionary/PRDs/009-search-settings).

Every endpoint needs a session and the ``yonetici`` role (Requirement 26); the service checks the
role again. Model connection settings are not here: an ``llm.`` key is an unknown setting.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.api.search_index_dependency import get_search_index
from app.db.session import get_db
from app.domain.accounts import ROLE_MANAGER
from app.schemas.errors import error_responses
from app.schemas.search.settings import (
    SearchIndexRebuilt,
    SearchIndexState,
    SearchSettings,
    SearchSettingsPatch,
    SearchSettingsSaved,
)
from app.services.search_index import SearchIndex
from app.services.search_settings_service import SearchSettingsService

_ERRORS = error_responses(
    {
        401: "not_authenticated: oturum yok",
        403: "forbidden: yonetici değil; cross_site_request: istek başka bir siteden geldi",
    }
)
_CHANGE_ERRORS = {
    500: "search_index_build_failed: indeks kurulamadı, hiçbir şey yazılmadı",
    503: "search_change_busy: başka bir değişiklik uygulanıyor",
}

router = APIRouter(
    tags=["search"],
    dependencies=[Depends(require_role(ROLE_MANAGER))],
    responses=_ERRORS,
)


def get_search_settings_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    index: Annotated[SearchIndex, Depends(get_search_index)],
) -> SearchSettingsService:
    return SearchSettingsService(session, index)


Service = Annotated[SearchSettingsService, Depends(get_search_settings_service)]


@router.get("/search-settings", response_model=SearchSettings)
async def read_settings(context: CurrentContext, service: Service) -> SearchSettings:
    """The settings schema, the 24 effective values and their defaults."""

    return await service.read(context)


@router.patch(
    "/search-settings",
    response_model=SearchSettingsSaved,
    responses=error_responses(
        {
            422: "search_setting_unknown: şemada olmayan anahtar; search_setting_invalid: tür ya "
            "da aralık; invalid_request: bozuk gövde",
            **_CHANGE_ERRORS,
        }
    ),
)
async def save_settings(
    body: SearchSettingsPatch, context: CurrentContext, service: Service
) -> SearchSettingsSaved:
    """Save the changed values; the engine is built with them before they are written."""

    return await service.save(context, body.values)


@router.get("/search-index", response_model=SearchIndexState)
async def search_index_state(context: CurrentContext, service: Service) -> SearchIndexState:
    """The serving index, a change in progress and the last failed attempt; no content."""

    return await service.index_state(context)


@router.post(
    "/search-index/rebuilds",
    response_model=SearchIndexRebuilt,
    responses=error_responses(_CHANGE_ERRORS),
)
async def rebuild_search_index(context: CurrentContext, service: Service) -> SearchIndexRebuilt:
    """Build the index again from the current inputs, even when they did not change."""

    return await service.rebuild(context)
