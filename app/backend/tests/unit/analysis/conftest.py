"""Fixtures of the analysis tests: the sample dictionary and the optional real one."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.domain.analysis import Dictionary
from tests.unit.analysis.workbooks import (
    SAMPLE_OBJECTS,
    SAMPLE_ROWS,
    import_workbook,
    xlsx_bytes,
)


@pytest.fixture
def sample_workbook() -> bytes:
    return xlsx_bytes({"Objeler": SAMPLE_OBJECTS, "Kolonlar": SAMPLE_ROWS})


@pytest.fixture
def sample_dictionary(sample_workbook: bytes) -> Dictionary:
    return import_workbook(sample_workbook)


@pytest.fixture
def real_workbook() -> bytes:
    """The real dictionary workbook, outside the repository; skipped when not given."""
    path = os.environ.get("DWHNAVIGATOR_PARITY_DICTIONARY", "")
    if not path or not Path(path).is_file():
        pytest.skip("Gerçek sözlük yok (DWHNAVIGATOR_PARITY_DICTIONARY verilmedi)")
    return Path(path).read_bytes()
