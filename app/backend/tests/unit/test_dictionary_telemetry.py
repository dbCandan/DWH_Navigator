"""Dictionary signals (data-dictionary 001-dictionary-management Gözlemlenebilirlik).

Names, fixed label sets and no content: a marker written into a table, a column and the file
name of an imported workbook appears in no span, attribute or metric label.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core import telemetry
from app.domain.dictionary import ImportChannel
from app.services.dictionary_service import DictionaryService
from tests.fakes.telemetry import TelemetryCapture
from tests.unit.analysis.workbooks import xlsx_bytes

pytestmark = pytest.mark.unit

MARKER = "SIZINTI7Q"


def test_names_and_label_sets(telemetry_capture: TelemetryCapture) -> None:
    for outcome in ("created", "unchanged", "invalid", "conflict", "free text"):
        with telemetry.dictionary_import_span("arayuz") as record:
            record.outcome = outcome
            record.row_count = 3
    with telemetry.dictionary_import_span("elsewhere"):
        pass
    telemetry.record_dictionary_export("dictionary")
    telemetry.record_dictionary_export("template")
    telemetry.record_dictionary_export(MARKER)
    telemetry.set_active_dictionary(1557, 87)

    assert {
        "dwhnavigator_dictionary_imports_total",
        "dwhnavigator_dictionary_import_duration_seconds",
        "dwhnavigator_dictionary_exports_total",
        "dwhnavigator_dictionary_active_columns",
        "dwhnavigator_dictionary_active_tables",
    } <= telemetry_capture.metric_names()
    imports = {
        (labels["outcome"], labels["channel"]): value
        for labels, value in telemetry_capture.points("dwhnavigator_dictionary_imports_total")
    }
    assert imports == {
        ("created", "arayuz"): 1,
        ("unchanged", "arayuz"): 1,
        ("invalid", "arayuz"): 1,
        ("conflict", "arayuz"): 1,
        ("other", "arayuz"): 1,
        ("error", "other"): 1,
    }
    assert telemetry_capture.value("dwhnavigator_dictionary_exports_total", kind="other") == 1
    assert telemetry_capture.value("dwhnavigator_dictionary_active_columns") == 1557
    assert telemetry_capture.value("dwhnavigator_dictionary_active_tables") == 87
    spans = telemetry_capture.spans("dictionary import")
    assert len(spans) == 6
    assert dict(spans[0].attributes or {}).keys() == {
        "dwhnavigator.dictionary.channel",
        "dwhnavigator.dictionary.outcome",
        "dwhnavigator.dictionary.row_count",
        "dwhnavigator.duration_ms",
    }


def _context() -> Any:
    return MagicMock()


async def test_an_import_puts_no_content_into_the_signals(
    telemetry_capture: TelemetryCapture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused workbook (an invalid one) runs the import path without a database."""

    service = DictionaryService.__new__(DictionaryService)
    actor = MagicMock(public_id="kisi-1", user_id=1)

    async def manager(_context: Any) -> tuple[Any, int]:
        return actor, 1

    monkeypatch.setattr(service, "_manager", manager)
    rows = [{"DatabaseName": MARKER, f"{MARKER}Baslik": MARKER}]
    data = xlsx_bytes({"Kolonlar": rows})

    async def read() -> tuple[str, bytes]:
        return f"{MARKER}.xlsx", data

    read_upload: Callable[[], Awaitable[tuple[str, bytes]]] = read
    with pytest.raises(Exception) as refused:
        await service.import_workbook(_context(), read_upload)
    assert getattr(refused.value, "code", "") == "dictionary_workbook_invalid"
    assert MARKER in getattr(refused.value, "message", "")  # only the uploader sees it
    assert MARKER not in telemetry_capture.everything()
    assert (
        telemetry_capture.value(
            "dwhnavigator_dictionary_imports_total", outcome="invalid", channel="arayuz"
        )
        == 1
    )
    await asyncio.sleep(0)


def test_the_channel_values_are_the_import_channels() -> None:
    # An update and a rollback have signals of their own (dictionary-sync).
    imports = {ImportChannel.SCREEN.value, ImportChannel.SCRIPT.value}
    assert imports == telemetry.DICTIONARY_CHANNELS
    assert telemetry.DICTIONARY_CHANNELS <= {c.value for c in ImportChannel}
