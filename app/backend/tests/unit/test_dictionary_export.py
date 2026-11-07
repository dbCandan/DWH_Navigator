"""The dictionary export (dictionary-management Requirement 12), and no way in through Excel.

The workbook parsing itself is the source's (tests/unit/analysis and the parity test).
"""

from importlib.util import find_spec
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

from app.infrastructure.excel.writer import formulas_as_text, workbook_bytes
from app.main import app
from app.services.analysis.dictionary_workbook import (
    COLUMN_FIELDS,
    OBJECT_FIELDS,
    export,
    from_workbook,
    load_dictionary,
)

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


def _sheets(rows: dict[str, list[list[object]]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name, values in rows.items():
        sheet = book.create_sheet(name)
        for row in values:
            sheet.append(row)
        formulas_as_text(sheet)  # a cell text starting with "=" stays a text
    return workbook_bytes(book)


def test_the_export_gives_the_template_back_and_keeps_texts() -> None:
    columns = [FULL_COLUMN | {"ColumnDescription": "=1+1", "Notlar": "ek"}]
    objects = [FULL_OBJECT | {"Sahip": "ekip"}]
    data = _sheets(
        {
            "Objeler": [list(objects[0]), list(objects[0].values())],
            "Kolonlar": [list(columns[0]), list(columns[0].values())],
        }
    )
    imported = from_workbook(data)
    exported = export(imported.objects, imported.columns)
    book = load_workbook(BytesIO(exported))
    assert book.sheetnames == ["Objeler", "Kolonlar"]
    assert [c.value for c in book["Kolonlar"][1]] == [*COLUMN_FIELDS, "Notlar"]
    assert [c.value for c in book["Objeler"][1]] == [*OBJECT_FIELDS, "Sahip"]
    assert book["Kolonlar"]["E2"].value == "=1+1" and book["Kolonlar"]["E2"].data_type == "s"
    assert book["Kolonlar"].freeze_panes == "A2" and book["Objeler"].freeze_panes == "A2"
    again = from_workbook(exported)
    assert again.digest == imported.digest
    assert again.objects == imported.objects and again.columns == imported.columns
    first = load_dictionary(imported.objects, imported.columns, imported.version, imported.digest)
    second = load_dictionary(again.objects, again.columns, imported.version, again.digest)
    assert first.columns == second.columns and first.version == second.version


def test_the_excel_import_and_the_template_left_the_product() -> None:
    assert find_spec("app.services.dictionary_import") is None
    paths = {path.rsplit("/dictionary", 1)[-1] for path in app.openapi()["paths"]}
    assert "/export" in paths
    assert "/imports" not in paths and "/template" not in paths
