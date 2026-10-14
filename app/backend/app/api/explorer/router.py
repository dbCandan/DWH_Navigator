"""Dictionary explorer endpoints (data-dictionary/PRDs/007-dictionary-explorer, API sözleşmesi).

No session: a valid ``X-Device-Id`` is enough (Decision 2, application-foundation
003-anonymous-visitor Requirement 3). Every endpoint reads the serving engine only:
none takes a lock, waits for an analysis or writes anything; the table search runs in a worker
thread so the event loop and the live streams never wait for it. Before the first index build they
answer ``503 search_index_not_ready`` (Requirement 19). No search text, table or column name reaches
a log, a metric or a trace.
"""

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status

from app.api.search_index_dependency import get_search_index
from app.api.visitor.dependencies import get_current_visitor
from app.core import telemetry
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.domain.analysis_records import QUERY_MAX_CHARS
from app.schemas.errors import error_responses
from app.schemas.explorer.tables import (
    Galaxy,
    TableDetail,
    TableSearch,
    TableSearchResult,
)
from app.services import explorer
from app.services.analysis.pipeline import Engine
from app.services.search_index import SearchIndex, search_index_not_ready

logger = logging.getLogger("app.explorer")

_ERRORS = error_responses(
    {
        400: "device_id_required: X-Device-Id eksik ya da UUID 4 değil",
        403: "tenant_forbidden: başka kiracı; cross_site_request: istek başka bir siteden geldi",
        429: "rate_limited: yeni ziyaretçi sınırı",
        503: "search_index_not_ready: ilk arama indeksi kuruluyor",
    }
)

router = APIRouter(
    prefix="/explorer",
    tags=["explorer"],
    dependencies=[Depends(get_current_visitor)],
    responses=_ERRORS,
)

Index = Annotated[SearchIndex, Depends(get_search_index)]


def get_explorer_index(request: Request) -> explorer.ExplorerIndex:
    tables: explorer.ExplorerIndex = request.app.state.explorer_index
    return tables


Tables = Annotated[explorer.ExplorerIndex, Depends(get_explorer_index)]


def _serving(index: SearchIndex, endpoint: str) -> Engine:
    if not index.is_serving:
        telemetry.record_explorer_request(endpoint, "not_ready")
        raise search_index_not_ready()
    return index.engine()


@router.get("/galaxy", response_model=Galaxy, response_model_by_alias=True)
async def read_galaxy(index: Index, tables: Tables) -> dict[str, Any]:
    """Every served table with its main dataset group, by name."""

    engine = _serving(index, "galaxy")
    rows = await asyncio.to_thread(tables.rows, engine)
    items = explorer.galaxy(rows)
    telemetry.record_explorer_request("galaxy", "ok")
    return {"items": items, "total": len(items)}


@router.post(
    "/table-searches",
    response_model=TableSearchResult,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    responses=error_responses({422: "query_too_long: 4000 karakterden uzun; invalid_request"}),
)
async def search_tables(body: TableSearch, index: Index, tables: Tables) -> dict[str, Any]:
    """The name, content and column-name layers of the source's table search; nothing is kept."""

    if len(body.query.strip()) > QUERY_MAX_CHARS:
        telemetry.record_explorer_request("search", "invalid")
        raise ApplicationError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "query_too_long",
            "Arama metni çok uzun (en fazla 4000 karakter).",
        )
    engine = _serving(index, "search")
    mode = explorer.search_mode(body.query)
    try:
        with telemetry.explorer_search_span(mode) as span:
            rows = await asyncio.to_thread(tables.rows, engine)
            result = await asyncio.to_thread(explorer.search, engine, rows, body.query)
            span.results = len(result["items"])
    except Exception:
        telemetry.record_explorer_request("search", "error")
        raise
    telemetry.record_explorer_request("search", "ok")
    counts = result["counts"]
    log_event(
        logger,
        "explorer.search",
        mode=mode,
        chars=len(body.query.strip()),
        name_results=counts.get("ad", 0),
        content_results=counts.get("içerik", 0),
        column_results=counts.get("kolon adı", 0),
        elapsed_ms=result["elapsed_ms"],
    )
    return result


@router.get(
    "/tables/{table_key:path}",
    response_model=TableDetail,
    response_model_by_alias=True,
    responses=error_responses({404: "table_not_found: tablo hizmetteki indekste yok"}),
)
async def read_table(table_key: str, index: Index) -> dict[str, Any]:
    """A table's columns in dictionary order and its join keys."""

    engine = _serving(index, "table")
    detail = explorer.table_detail(engine, table_key)
    if detail is None:
        telemetry.record_explorer_request("table", "not_found")
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "table_not_found", "Kayıt bulunamadı")
    telemetry.record_explorer_request("table", "ok")
    return detail
