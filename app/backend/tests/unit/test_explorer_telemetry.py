"""Dictionary explorer signals (data-dictionary 007-dictionary-explorer Gözlemlenebilirlik).

The request counter with its fixed endpoint and outcome sets, the search duration by mode, one
content-free ``explorer search`` span per table search and the ``explorer.search`` event: no
search text, table or column name reaches a span, a metric label or a log line.
"""

import json
import logging
from typing import Any

import pytest

from app.api.explorer import router as explorer_api
from app.core.errors import ApplicationError
from app.schemas.explorer.tables import TableSearch
from app.services.analysis.pipeline import Engine
from app.services.explorer import ExplorerIndex
from tests.fakes.telemetry import TelemetryCapture
from tests.parity.fake_model import FakeAnalyst
from tests.parity.harness import STOPWORDS, TERMS, WORKBOOK
from tests.parity.run_target import TargetSide

pytestmark = pytest.mark.unit

MARKER = "SIZINTI7Q"
REQUESTS = "dwhnavigator_explorer_requests_total"
DURATION = "dwhnavigator_explorer_search_duration_seconds"


class ServingIndex:
    def __init__(self, engine: Engine | None) -> None:
        self._engine = engine

    @property
    def is_serving(self) -> bool:
        return self._engine is not None

    def engine(self) -> Engine:
        assert self._engine is not None
        return self._engine


@pytest.fixture(scope="module")
def engine() -> Engine:
    side = TargetSide()
    dictionary, _ = side.parse_dictionary(WORKBOOK.read_bytes())
    groups, stop = side.word_lists(TERMS, STOPWORDS)
    return side.engine(dictionary, {}, groups, stop, side.client(FakeAnalyst()))


def _events(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [
        dict(getattr(r, "structured_fields", {}))
        for r in caplog.records
        if r.name == "app.explorer"
    ]


async def test_names_labels_and_no_content(
    engine: Engine, telemetry_capture: TelemetryCapture, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.explorer")
    index, tables = ServingIndex(engine), ExplorerIndex()
    table = next(iter(engine.objects))
    name = engine.objects[table].features[0].col.object_name
    column = engine.objects[table].features[0].col.column

    galaxy = await explorer_api.read_galaxy(index, tables)  # type: ignore[arg-type]
    assert galaxy["total"] == len(galaxy["items"]) == len(engine.objects)
    for query in ("", "ab", f"{MARKER} {name} {column} kredi kartı limiti"):
        await explorer_api.search_tables(TableSearch(query=query), index, tables)  # type: ignore[arg-type]
    await explorer_api.read_table(table, index)  # type: ignore[arg-type]
    with pytest.raises(ApplicationError) as missing:
        await explorer_api.read_table(f"{MARKER}.x.y", index)  # type: ignore[arg-type]
    assert missing.value.code == "table_not_found"
    with pytest.raises(ApplicationError) as too_long:
        await explorer_api.search_tables(TableSearch(query="x" * 4001), index, tables)  # type: ignore[arg-type]
    assert too_long.value.code == "query_too_long"
    with pytest.raises(ApplicationError) as not_ready:
        await explorer_api.read_galaxy(ServingIndex(None), tables)  # type: ignore[arg-type]
    assert not_ready.value.code == "search_index_not_ready"

    requests = {
        (labels["endpoint"], labels["outcome"]): value
        for labels, value in telemetry_capture.points(REQUESTS)
    }
    assert requests == {
        ("galaxy", "ok"): 1,
        ("search", "ok"): 3,
        ("table", "ok"): 1,
        ("table", "not_found"): 1,
        ("search", "invalid"): 1,
        ("galaxy", "not_ready"): 1,
    }
    modes = {labels["mode"] for labels, _ in telemetry_capture.points(DURATION)}
    assert modes == {"browse", "name_only", "full"}
    spans = telemetry_capture.spans("explorer search")
    assert [dict(s.attributes or {})["dwhnavigator.explorer.mode"] for s in spans] == [
        "browse",
        "name_only",
        "full",
    ]
    assert all("dwhnavigator.explorer.results" in (s.attributes or {}) for s in spans)
    events = _events(caplog)
    assert [e["mode"] for e in events if e["event"] == "explorer.search"] == [
        "browse",
        "name_only",
        "full",
    ]
    everything = json.dumps(
        [
            *[dict(s.attributes or {}) for s in telemetry_capture.spans()],
            *[s.name for s in telemetry_capture.spans()],
            *[
                labels
                for name in (REQUESTS, DURATION)
                for labels, _ in telemetry_capture.points(name)
            ],
            *events,
        ],
        ensure_ascii=False,
    )
    for secret in (MARKER, name, column, "kredi"):
        assert secret not in everything, secret
