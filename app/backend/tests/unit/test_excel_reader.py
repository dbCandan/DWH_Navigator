"""The shared safe Excel reader (data-dictionary 001-dictionary-management Requirement 2)."""

import zipfile
from io import BytesIO

import pytest
from openpyxl import Workbook
from openpyxl.xml import DEFUSEDXML

from app.infrastructure.excel import reader
from app.infrastructure.excel.reader import (
    TooManyColumns,
    TooManyRows,
    WorkbookTooLarge,
    WorkbookUnreadable,
    open_workbook,
)
from app.infrastructure.excel.writer import formulas_as_text, workbook_bytes

pytestmark = pytest.mark.unit


def _book(sheets: dict[str, list[list[object]]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    return workbook_bytes(book)


def test_workbook_xml_is_parsed_with_defusedxml() -> None:
    assert DEFUSEDXML is True


def test_bytes_that_are_not_a_workbook_are_unreadable() -> None:
    for data in (b"", b"not excel", b"PK\x03\x04broken"):
        with pytest.raises(WorkbookUnreadable), open_workbook(data):
            pass
    # A zip package that is not a workbook.
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("hello.txt", "merhaba")
    with pytest.raises(WorkbookUnreadable), open_workbook(buffer.getvalue()):
        pass


def test_a_package_that_unpacks_beyond_the_limit_is_refused_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _book({"Kolonlar": [["a"], ["x" * 5000]]})
    monkeypatch.setattr(reader, "MAX_UNPACKED_BYTES", 1000)
    with pytest.raises(WorkbookTooLarge), open_workbook(data):
        pass


def test_only_named_sheets_are_read_and_every_name_is_known() -> None:
    data = _book({"Başka": [["x"]], "Kolonlar": [["a", "b"], [1, 2.0]]})
    with open_workbook(data) as book:
        assert book.sheet_names == ["Başka", "Kolonlar"]
        assert book.rows("Kolonlar", max_rows=10, max_cols=5) == [
            ["a", "b", None, None, None],
            [1, 2, None, None, None],
        ]


def test_rows_beyond_the_limit_are_refused_only_when_filled() -> None:
    rows: list[list[object]] = [["h"], *([["v"]] * 3), [None], [None]]
    data = _book({"S": rows})
    with open_workbook(data) as book:
        assert len(book.rows("S", max_rows=4, max_cols=1)) == 4  # trailing empties not counted
        with pytest.raises(TooManyRows):
            book.rows("S", max_rows=3, max_cols=1)


def test_a_header_beyond_the_column_limit_is_refused_wider_data_is_not_read() -> None:
    wide_header = _book({"S": [["c"] * 4]})
    with open_workbook(wide_header) as book:
        with pytest.raises(TooManyColumns) as refused:
            book.rows("S", max_rows=5, max_cols=3, refuse_wider_header=True)
        assert refused.value.sheet == "S"
    wide_data = _book({"S": [["a", "b", "c"], [1, 2, 3, 4, 5]]})
    with open_workbook(wide_data) as book:
        rows = book.rows("S", max_rows=5, max_cols=3, refuse_wider_header=True)
        assert rows == [["a", "b", "c"], [1, 2, 3]]


def test_a_text_starting_with_equals_is_written_as_text() -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(["=1+1", '=HYPERLINK("http://x")', "metin"])
    formulas_as_text(sheet)
    data = workbook_bytes(book)
    with open_workbook(data) as opened:
        assert opened.rows(opened.sheet_names[0], max_rows=5, max_cols=3) == [
            ["=1+1", '=HYPERLINK("http://x")', "metin"]
        ]
