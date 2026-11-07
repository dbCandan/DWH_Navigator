"""Dictionary signals (data-dictionary 001-dictionary-management Gözlemlenebilirlik).

Names and fixed label sets. The import's signals are gone with the import (dictionary-sync
Requirement 13).
"""

import pytest

from app.core import telemetry
from tests.fakes.telemetry import TelemetryCapture

pytestmark = pytest.mark.unit

MARKER = "SIZINTI7Q"


def test_names_and_label_sets(telemetry_capture: TelemetryCapture) -> None:
    telemetry.record_dictionary_export("dictionary")
    telemetry.record_dictionary_export(MARKER)
    telemetry.set_active_dictionary(1557, 87)

    names = telemetry_capture.metric_names()
    assert {
        "dwhnavigator_dictionary_exports_total",
        "dwhnavigator_dictionary_active_columns",
        "dwhnavigator_dictionary_active_tables",
    } <= names
    assert "dwhnavigator_dictionary_imports_total" not in names
    assert telemetry_capture.value("dwhnavigator_dictionary_exports_total", kind="dictionary") == 1
    assert telemetry_capture.value("dwhnavigator_dictionary_exports_total", kind="other") == 1
    assert telemetry_capture.value("dwhnavigator_dictionary_active_columns") == 1557
    assert telemetry_capture.value("dwhnavigator_dictionary_active_tables") == 87
    assert MARKER not in telemetry_capture.everything()
