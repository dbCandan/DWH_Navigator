"""Checking an uploaded dictionary workbook and writing the template back (dictionary-management).

Requirement 1 (template), 2 (limits), 3-6 (headers, cells, warnings, messages), 7 (version and
digest) and 12 (export); the parsing itself is the source's (tests/unit/analysis and the parity
test).
"""

from io import BytesIO
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook

from app.infrastructure.excel import reader
from app.infrastructure.excel.writer import formulas_as_text, workbook_bytes
from app.services import dictionary_import
from app.services.analysis.dictionary_workbook import (
    COLUMN_FIELDS,
    OBJECT_FIELDS,
    export,
    load_dictionary,
)
from app.services.dictionary_import import (
    DictionaryWorkbookInvalid,
    check_dictionary_workbook,
)
from tests.unit.analysis.workbooks import SAMPLE_OBJECTS, SAMPLE_ROWS, xlsx_bytes

pytestmark = pytest.mark.unit

FULL_COLUMN = {
    "DatabaseName": "DB",
    "SchemaName": "S",
    "ObjectName": "T",
    "ColumnName": "C",
    "ColumnDescription": "Açıklama",
    "Synonyms": "eş",
    "Role": "Ölçü",
    "Summary": "Özet",
}
FULL_OBJECT = dict.fromkeys(OBJECT_FIELDS, "") | {"ObjectKey": "DB.S.T", "DatasetGroup": "G"}


def _invalid(data: bytes) -> str:
    with pytest.raises(DictionaryWorkbookInvalid) as refused:
        check_dictionary_workbook(data)
    return refused.value.message


def _sheets(rows: dict[str, list[list[Any]]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name, values in rows.items():
        sheet = book.create_sheet(name)
        for row in values:
            sheet.append(row)
        formulas_as_text(sheet)  # a cell text starting with "=" stays a text
    return workbook_bytes(book)


def test_the_sample_imports_with_the_sources_records_and_version() -> None:
    data = xlsx_bytes({"Objeler": SAMPLE_OBJECTS, "Kolonlar": SAMPLE_ROWS})
    checked = check_dictionary_workbook(data)
    imported = checked.imported
    assert imported.column_count == 3 and imported.object_count == 2
    assert imported.version.endswith("-4") and checked.row_count == 4
    assert imported.columns[0]["DatabaseName"] == "EDWDM"  # DAtabaseName renamed
    assert imported.columns[0]["ObjectName"] == "vCardLimitFullness"  # trimmed
    assert checked.column_extra_headers == [] and checked.object_extra_headers == []


def test_a_missing_template_column_is_a_new_warning_before_the_row_warnings() -> None:
    rows = [{k: v for k, v in r.items()} for r in SAMPLE_ROWS]
    for row in rows:
        row.pop("Synonyms")
        row["Rol"] = "Ölçü"  # a Turkish spelling is not recognised: an extra column
    objects = [{"ObjectKey": o["ObjectKey"], "Grain": "gün"} for o in SAMPLE_OBJECTS]
    checked = check_dictionary_workbook(xlsx_bytes({"Objeler": objects, "Kolonlar": rows}))
    warnings = checked.imported.warnings
    assert warnings[:8] == [
        "“Objeler” sayfasında şablondaki “ObjectDescription” sütunu yok; bu alan boş aktarıldı.",
        "“Objeler” sayfasında şablondaki “KeyColumns” sütunu yok; bu alan boş aktarıldı.",
        "“Objeler” sayfasında şablondaki “TimeColumns” sütunu yok; bu alan boş aktarıldı.",
        "“Objeler” sayfasında şablondaki “BusinessDomain” sütunu yok; bu alan boş aktarıldı.",
        "“Objeler” sayfasında şablondaki “DatasetGroup” sütunu yok; bu alan boş aktarıldı.",
        "“Kolonlar” sayfasında şablondaki “Synonyms” sütunu yok; bu alan boş aktarıldı.",
        "“Kolonlar” sayfasında şablondaki “Role” sütunu yok; bu alan boş aktarıldı.",
        "“Kolonlar” sayfasında şablondaki “Summary” sütunu yok; bu alan boş aktarıldı.",
    ]
    assert warnings[8].startswith("Tekrarlanan kolon")
    assert checked.column_extra_headers == ["Rol"]
    assert all(c["Role"] == "" and c["Rol"] == "Ölçü" for c in checked.imported.columns)


def test_object_key_and_the_name_triple_stand_for_each_other() -> None:
    columns = [FULL_COLUMN]
    only_key = [{"ObjectKey": "DB.S.T"} | {f: "" for f in OBJECT_FIELDS[4:]}]
    only_names = [{f: "x" for f in OBJECT_FIELDS[1:]}]
    neither = [{"ObjectDescription": "d"} | {f: "" for f in OBJECT_FIELDS[5:]}]

    def missing(objects: list[dict[str, str]]) -> list[str]:
        warnings = check_dictionary_workbook(
            xlsx_bytes({"Objeler": objects, "Kolonlar": columns})
        ).imported.warnings
        return [w.split("“")[2].split("”")[0] for w in warnings if "sütunu yok" in w]

    assert missing(only_key) == []
    assert missing(only_names) == []
    assert missing(neither) == ["ObjectKey", "DatabaseName", "SchemaName", "ObjectName"]


def test_without_objeler_its_warning_comes_first() -> None:
    warnings = check_dictionary_workbook(
        xlsx_bytes({"Kolonlar": [{k: v for k, v in FULL_COLUMN.items() if k != "Summary"}]})
    ).imported.warnings
    assert warnings == [
        "“Objeler” sayfası yok: tablo açıklamaları ve gruplar olmadan aktarıldı.",
        "“Kolonlar” sayfasında şablondaki “Summary” sütunu yok; bu alan boş aktarıldı.",
    ]


def test_the_sources_messages_for_a_workbook_off_the_template() -> None:
    assert _invalid(b"not a workbook") == "Dosya Excel (.xlsx) olarak okunamadı."
    assert _invalid(_sheets({"Sayfa1": [["a"]], "Başka": [["b"]]})) == (
        "“Kolonlar” sayfası yok (dosyadaki sayfalar: Sayfa1, Başka). Şablonu indirip ona göre "
        "doldurun."
    )
    assert _invalid(_sheets({"Kolonlar": [["DatabaseName"]]})) == "“Kolonlar” sayfasında kolon yok."
    assert _invalid(_sheets({"Kolonlar": [["DatabaseName", "X"], ["a", "b"]]})).startswith(
        "Sözlükte zorunlu kolon bulunamadı: schemaname (mevcut: DatabaseName, X)"
    )
    assert _invalid(_sheets({"Kolonlar": [list(COLUMN_FIELDS), ["DB", "", "T", "C", "d"]]})) == (
        "Geçerli kolon satırı yok (veritabanı, şema, obje ve kolon adı dolu olmalı)."
    )


def test_the_dictionarys_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    header = list(COLUMN_FIELDS)
    wide = _sheets(
        {"Kolonlar": [[*header, *[f"Ek{i}" for i in range(93)]], list(FULL_COLUMN.values())]}
    )
    assert _invalid(wide) == "“Kolonlar” sayfasında en fazla 100 sütun olabilir."
    hundred = _sheets(
        {"Kolonlar": [[*header, *[f"Ek{i}" for i in range(92)]], list(FULL_COLUMN.values())]}
    )
    assert check_dictionary_workbook(hundred).imported.column_count == 1

    monkeypatch.setattr(dictionary_import, "MAX_IMPORT_ROWS", 3)
    rows = [header, *[["DB", "S", "T", f"C{i}", "d"] for i in range(3)]]
    assert check_dictionary_workbook(_sheets({"Kolonlar": [*rows, [None]]})).row_count == 3
    message = _invalid(_sheets({"Kolonlar": [*rows, ["DB", "S", "T", "C9", "d"]]}))
    assert message == "Dosyada çok fazla satır var (en fazla 200.000)."

    monkeypatch.setattr(reader, "MAX_UNPACKED_BYTES", 1000)
    assert _invalid(hundred) == "Dosya açıldığında çok büyük (en fazla 100 MB)."


def test_sheets_other_than_the_template_are_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dictionary_import, "MAX_IMPORT_ROWS", 2)
    data = _sheets(
        {
            "Notlar": [["x"]] * 50,  # longer than the limit, but never read
            "Kolonlar": [list(COLUMN_FIELDS), list(FULL_COLUMN.values())],
        }
    )
    assert check_dictionary_workbook(data).imported.column_count == 1


def test_the_export_gives_the_template_back_and_keeps_texts() -> None:
    columns = [FULL_COLUMN | {"ColumnDescription": "=1+1", "Notlar": "ek"}]
    objects = [FULL_OBJECT | {"Sahip": "ekip"}]
    data = _sheets(
        {
            "Objeler": [list(objects[0]), list(objects[0].values())],
            "Kolonlar": [list(columns[0]), list(columns[0].values())],
        }
    )
    checked = check_dictionary_workbook(data)
    imported = checked.imported
    exported = export(imported.objects, imported.columns)
    book = load_workbook(BytesIO(exported))
    assert book.sheetnames == ["Objeler", "Kolonlar"]
    assert [c.value for c in book["Kolonlar"][1]] == [*COLUMN_FIELDS, "Notlar"]
    assert [c.value for c in book["Objeler"][1]] == [*OBJECT_FIELDS, "Sahip"]
    assert book["Kolonlar"]["E2"].value == "=1+1" and book["Kolonlar"]["E2"].data_type == "s"
    assert book["Kolonlar"].freeze_panes == "A2" and book["Objeler"].freeze_panes == "A2"
    again = check_dictionary_workbook(exported).imported
    assert again.digest == imported.digest
    assert again.objects == imported.objects and again.columns == imported.columns
    first = load_dictionary(imported.objects, imported.columns, imported.version, imported.digest)
    second = load_dictionary(again.objects, again.columns, imported.version, again.digest)
    assert first.columns == second.columns and first.version == second.version


def test_the_empty_template_has_the_two_header_rows() -> None:
    book = load_workbook(BytesIO(export(None, None)))
    assert book.sheetnames == ["Objeler", "Kolonlar"]
    assert [[c.value for c in row] for row in book["Objeler"].iter_rows()] == [list(OBJECT_FIELDS)]
    assert [[c.value for c in row] for row in book["Kolonlar"].iter_rows()] == [list(COLUMN_FIELDS)]
    assert book["Objeler"].freeze_panes == "A2"
