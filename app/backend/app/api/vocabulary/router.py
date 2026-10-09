"""Word list endpoints of the Kelimeler page (data-dictionary/PRDs/002-vocabulary-management).

``{list}`` is ``terms`` or ``stopwords``; any other value is 404 ``vocabulary_list_not_found``.
Every endpoint needs a session and the ``yonetici`` role; the service checks the role again.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response
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
from app.schemas.errors import error_responses
from app.schemas.vocabulary.lists import (
    VocabularyListSave,
    VocabularyListSaved,
    VocabularyListState,
)
from app.services.search_index import SearchIndex
from app.services.vocabulary_service import VocabularyService, parse_list_name

_ERRORS = error_responses(
    {
        401: "not_authenticated: oturum yok",
        403: "forbidden: yonetici değil; cross_site_request: istek başka bir siteden geldi",
        404: "vocabulary_list_not_found: liste adı terms ya da stopwords değil",
    }
)
_CHECKS = (
    "vocabulary_items_invalid, vocabulary_too_many_items, vocabulary_term_empty, "
    "vocabulary_term_without_equivalents, vocabulary_term_duplicate, "
    "vocabulary_stopword_not_single_word, vocabulary_value_too_long, "
    "vocabulary_too_many_equivalents: liste denetimi; invalid_request: alan türü"
)
_CHANGE_ERRORS = {
    500: "search_index_build_failed: indeks kurulamadı, hiçbir şey yazılmadı",
    503: "search_change_busy: başka bir değişiklik uygulanıyor",
}

router = APIRouter(
    prefix="/vocabulary",
    tags=["vocabulary"],
    dependencies=[Depends(require_role(ROLE_MANAGER))],
    responses=_ERRORS,
)


def get_vocabulary_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    index: Annotated[SearchIndex, Depends(get_search_index)],
) -> VocabularyService:
    return VocabularyService(session, index)


Service = Annotated[VocabularyService, Depends(get_vocabulary_service)]


@router.get("/{list_name}", response_model=VocabularyListState)
async def read_list(
    list_name: str, context: CurrentContext, service: Service
) -> VocabularyListState:
    """The list's items in their stored order and its revision."""

    return await service.read(context, parse_list_name(list_name))


@router.put(
    "/{list_name}",
    response_model=VocabularyListSaved,
    responses=error_responses({422: _CHECKS, **_CHANGE_ERRORS}),
)
async def save_list(
    list_name: str, body: VocabularyListSave, context: CurrentContext, service: Service
) -> VocabularyListSaved:
    """Replace the whole list; the index is rebuilt with it before it is written."""

    return await service.save(context, parse_list_name(list_name), body.items)


@router.get("/{list_name}/export", response_class=Response, responses={200: EXCEL_RESPONSE})
async def export_list(list_name: str, context: CurrentContext, service: Service) -> Response:
    """The saved list as a one-sheet workbook, named after the Istanbul time."""

    filename, data = await service.export(context, parse_list_name(list_name))
    return excel_download(filename, data)


@router.post(
    "/{list_name}/import",
    response_model=VocabularyListSaved,
    openapi_extra=EXCEL_REQUEST_BODY,
    responses=error_responses(
        {
            413: "upload_too_large: gövde 20 MB'tan büyük",
            415: "unsupported_media_type: gövde Excel değil",
            422: "vocabulary_file_empty, vocabulary_workbook_unreadable, "
            "vocabulary_workbook_too_many_rows, vocabulary_workbook_column_missing, "
            f"vocabulary_workbook_empty: dosya; {_CHECKS}",
            **_CHANGE_ERRORS,
        }
    ),
)
async def import_list(
    list_name: str,
    request: Request,
    context: CurrentContext,
    service: Service,
    x_filename: Annotated[str | None, Header(alias="X-Filename")] = None,
) -> VocabularyListSaved:
    """Replace the list with a workbook's rows, checked like a save."""

    del x_filename  # documented here; the list keeps no file name

    async def read_upload() -> bytes:
        upload = await read_excel_upload(
            request, empty_code="vocabulary_file_empty", default_name="liste.xlsx"
        )
        return upload.data

    return await service.import_workbook(context, parse_list_name(list_name), read_upload)
