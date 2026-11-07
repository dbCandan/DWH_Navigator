"""Dictionary endpoints of the admin screen (data-dictionary/PRDs/001-dictionary-management).

Every endpoint needs a session and the ``yonetici`` role (Decision 3; the super admin passes
centrally); the service re-reads the account and checks the role again. The HTTP log and trace
carry the route template only, never a table key or a file name.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.api.excel_transfer import EXCEL_RESPONSE, excel_download
from app.api.search_index_dependency import get_search_index
from app.db.session import get_db
from app.domain.accounts import ROLE_MANAGER
from app.schemas.dictionary.management import (
    DictionaryState,
    DictionaryTableRecords,
    DictionaryTablesPage,
)
from app.schemas.errors import error_responses
from app.services.dictionary_service import DictionaryService
from app.services.search_index import SearchIndex

_ERRORS = error_responses(
    {
        401: "not_authenticated: oturum yok",
        403: "forbidden: yonetici değil; cross_site_request: istek başka bir siteden geldi",
    }
)
_NOT_IMPORTED = "dictionary_not_imported: etkin sözlük sürümü yok"

router = APIRouter(
    prefix="/dictionary",
    tags=["dictionary"],
    dependencies=[Depends(require_role(ROLE_MANAGER))],
    responses=_ERRORS,
)


def get_dictionary_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    index: Annotated[SearchIndex, Depends(get_search_index)],
) -> DictionaryService:
    return DictionaryService(session, index)


Service = Annotated[DictionaryService, Depends(get_dictionary_service)]


@router.get("", response_model=DictionaryState)
async def dictionary_state(context: CurrentContext, service: Service) -> DictionaryState:
    """The active and previous version summaries and the serving index's dictionary version."""

    return await service.state(context)


@router.get(
    "/tables",
    response_model=DictionaryTablesPage,
    responses=error_responses({404: _NOT_IMPORTED, 422: "invalid_request: sayfa değerleri"}),
)
async def dictionary_tables(
    context: CurrentContext,
    service: Service,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000)] = 1000,
) -> DictionaryTablesPage:
    """Tables of the active version as imported, by ``DB.Şema.Obje`` in code point order."""

    return await service.tables(context, page, page_size)


@router.get(
    "/tables/{table_key:path}",
    response_model=DictionaryTableRecords,
    responses=error_responses(
        {404: f"{_NOT_IMPORTED}; dictionary_table_not_found: anahtar için Kolonlar kaydı yok"}
    ),
)
async def dictionary_table(
    table_key: str, context: CurrentContext, service: Service
) -> DictionaryTableRecords:
    """One table's Objeler record and Kolonlar records as imported, in sheet order."""

    return await service.table(context, table_key)


@router.get(
    "/export",
    response_class=Response,
    responses={200: EXCEL_RESPONSE, **error_responses({404: _NOT_IMPORTED})},
)
async def export_dictionary(context: CurrentContext, service: Service) -> Response:
    """The active version in the template, named after the Istanbul time."""

    filename, data = await service.export(context)
    return excel_download(filename, data)
