"""ADR-049/050: a workbook in the dictionary template -> stored records -> the engine's
dictionary. Storage, export and the import endpoint belong to dictionary-management."""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.analysis import DictColumn
from app.services.analysis import dictionary_workbook as dw
from app.services.analysis.loader import (
    build_columns,
    object_profiles,
    read_workbook,
    records,
)
from tests.unit.analysis.workbooks import xlsx_bytes

pytestmark = pytest.mark.unit


def parse_workbook(data: bytes) -> list[DictColumn]:
    """The workbook as the template parser reads it — what an import must keep."""
    sheets = read_workbook(data)
    profiles = object_profiles(records(sheets.get("Objeler", [])))
    columns, _ = build_columns(list(records(sheets["Kolonlar"])),
                               {k: p.group for k, p in profiles.items() if p.group})  # fmt: skip
    return columns


def test_import_keeps_the_workbook(sample_workbook: bytes) -> None:
    imported = dw.from_workbook(sample_workbook)
    assert imported.column_count == 3 and imported.object_count == 2
    assert any("Tekrarlanan" in w for w in imported.warnings)
    d = dw.load_dictionary(imported.objects, imported.columns, imported.version, imported.digest)
    assert d.columns == parse_workbook(sample_workbook)
    assert d.version == imported.version and d.version.endswith("-4")
    assert d.source_path == "dictionary.jsonl"
    assert len(imported.objects) == 2 and len(imported.columns) == 4
    # "DAtabaseName" stored under its template name
    assert "DatabaseName" in imported.columns[-1] and "DAtabaseName" not in imported.columns[-1]


def test_hand_edited_records_get_their_own_version(sample_workbook: bytes) -> None:
    imported = dw.from_workbook(sample_workbook)
    before = dw.load_dictionary(
        imported.objects, imported.columns, imported.version, imported.digest
    ).version
    edited = [{**c, "ColumnDescription": "Değişti."} for c in imported.columns]
    after = dw.load_dictionary(imported.objects, edited, imported.version, imported.digest)
    assert after.version not in (before, "")
    assert after.version.endswith(f"-{len(edited)}")


def test_empty_dictionary() -> None:
    d = dw.empty_dictionary()
    assert (d.columns, d.version, d.source_path) == ([], "", "dictionary.jsonl")


@pytest.mark.parametrize(
    ("sheets", "message"),
    [
        ({"Sayfa1": [{"a": 1}]}, "Kolonlar"),
        ({"Kolonlar": [{"DatabaseName": None, "SchemaName": "S", "ObjectName": "T",
                        "ColumnName": "C", "ColumnDescription": "d"}]}, "Geçerli kolon"),
        ({"Kolonlar": [{"SchemaName": "S"}]}, "zorunlu kolon"),
    ],
)  # fmt: skip
def test_bad_workbooks_are_refused(sheets: dict[str, list[dict[str, Any]]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dw.from_workbook(xlsx_bytes(sheets))


def test_not_a_workbook_is_refused() -> None:
    with pytest.raises(ValueError, match=r"^Dosya Excel \(\.xlsx\) olarak okunamadı\.$"):
        dw.from_workbook(b"not a workbook")


def test_too_many_rows_names_the_limit_in_turkish(monkeypatch: pytest.MonkeyPatch) -> None:
    """dictionary-management Requirement 5: the limit is written with the Turkish separator."""
    monkeypatch.setattr(dw, "MAX_IMPORT_ROWS", 2_000)
    rows = [
        {"DatabaseName": "DB", "SchemaName": "S", "ObjectName": "T", "ColumnName": f"C{i}",
         "ColumnDescription": "d"}
        for i in range(2_001)
    ]  # fmt: skip
    with pytest.raises(ValueError, match=r"^Dosyada çok fazla satır var \(en fazla 2\.000\)\.$"):
        dw.from_workbook(xlsx_bytes({"Kolonlar": rows}))
