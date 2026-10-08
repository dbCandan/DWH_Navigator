"""Dictionary endpoints of the admin screen (data-dictionary/PRDs/001-dictionary-management).

Every endpoint needs a session and the ``yonetici`` role (Decision 3; the super admin passes
centrally); the service re-reads the account and checks the role again. The HTTP log and trace
carry the route template only, never a table key or a file name.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.api.excel_transfer import (
    EXCEL_REQUEST_BODY,
    EXCEL_RESPONSE,
    excel_download,
    read_excel_upload,
)
from app.api.search_index_dependency import get_search_index
from app.db.session import get_db
from app.domain.accounts import ROLE_MANAGER
from app.domain.dictionary import DEFAULT_SOURCE_NAME
from app.schemas.dictionary.management import (
    DictionaryImported,
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


@router.post(
    "/imports",
    response_model=DictionaryImported,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=EXCEL_REQUEST_BODY,
    responses={
        200: {"model": DictionaryImported, "description": "İçerik etkin sürümle aynı"},
        **error_responses(
            {
                409: "dictionary_import_in_progress: başka bir içe aktarma yazıyor",
                413: "upload_too_large: gövde 20 MB'tan büyük",
                415: "unsupported_media_type: gövde Excel değil",
                422: "dictionary_file_empty: gövde boş; dictionary_workbook_invalid: dosya "
                "şablona uymuyor",
                500: "search_index_build_failed: indeks kurulamadı, hiçbir şey yazılmadı",
                503: "search_change_busy: başka bir değişiklik uygulanıyor",
            }
        ),
    },
)
async def import_dictionary(
    request: Request,
    context: CurrentContext,
    service: Service,
    x_filename: Annotated[str | None, Header(alias="X-Filename")] = None,
) -> JSONResponse:
    """Import a workbook in the template; 201 with a new version, 200 when the content is the
    active version's (Requirement 7)."""

    del x_filename  # documented here, read with the body

    async def read_upload() -> tuple[str, bytes]:
        upload = await read_excel_upload(
            request,
            empty_code="dictionary_file_empty",
            default_name=DEFAULT_SOURCE_NAME,
        )
        return upload.filename, upload.data

    imported = await service.import_workbook(context, read_upload)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED if imported.changed else status.HTTP_200_OK,
        content=imported.model_dump(mode="json"),
    )


@router.get(
    "/export",
    response_class=Response,
    responses={200: EXCEL_RESPONSE, **error_responses({404: _NOT_IMPORTED})},
)
async def export_dictionary(context: CurrentContext, service: Service) -> Response:
    """The active version in the template, named after the Istanbul time."""

    filename, data = await service.export(context)
    return excel_download(filename, data)


@router.get("/template", response_class=Response, responses={200: EXCEL_RESPONSE})
async def dictionary_template(context: CurrentContext, service: Service) -> Response:
    """The empty template: both sheets with their header rows."""

    filename, data = await service.template(context)
    return excel_download(filename, data)
