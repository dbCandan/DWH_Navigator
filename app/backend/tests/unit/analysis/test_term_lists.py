"""Reading a term list (data-dictionary 005-list-search Requirement 1-3; Acceptance 1).

The source's ``tests/test_loader.py`` list tests with only their import paths changed, and the
added ones: the 2,001 and 2,002 row limits, too many rows on a second sheet, data beyond the 50th
column, an unpacked size beyond 100 MB, an old ``.xls`` and a ``.csv`` file, and the codes.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.domain.term_lists import Rejection, TermListRejected
from app.services.analysis.loader import MAX_TERMS, load_term_list, parse_term_sheet
from tests.unit.analysis.workbooks import xlsx_bytes

pytestmark = pytest.mark.unit


def sheet_bytes(*sheets: tuple[str, list[list[object]]]) -> bytes:
    book = Workbook()
    book.remove(book.active)  # type: ignore[arg-type]
    for title, rows in sheets:
        ws = book.create_sheet(title)
        for row in rows:
            ws.append(row)
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def test_term_list_parsing() -> None:
    """ADR-033: one fixed format — column A, row 1 is the header, a term per row below."""
    nan = float("nan")
    rows = [["Terim"], [" kredi  kartı "], [None], [nan], ["Kredi kartı"], ["mevduat"]]
    r = parse_term_sheet(rows)
    assert r.terms == ["kredi kartı", "mevduat"] and r.header == "Terim"
    assert r.notes == [
        "2 boş satır atlandı.",
        "1 tekrar eden terim atlandı (ilk geçtiği satır arandı).",
    ]

    # the first row is always the header, even when it reads like a term — and it is said
    r = parse_term_sheet([["kredi kartı"], ["mevduat"]])
    assert r.terms == ["mevduat"]
    assert r.notes == ["İlk satır (“kredi kartı”) başlık sayıldı ve aranmadı."]
    assert parse_term_sheet([["Terim"], ["x"]], ["Sayfa2"]).notes == [
        "Yalnız ilk sayfa okundu; şu sayfalardaki veriler alınmadı: Sayfa2."]  # fmt: skip


def test_term_list_file() -> None:
    data = xlsx_bytes({"Liste": [{"Terim": "kart"}, {"Terim": "mevduat"}], "Boş": []})
    r = load_term_list(data)
    assert r.terms == ["kart", "mevduat"] and r.notes == []  # an empty sheet is not reported
    with pytest.raises(ValueError, match="Excel"):
        load_term_list(b"not a workbook")
    huge = xlsx_bytes({"Liste": [{"Terim": f"t{i}"} for i in range(2500)]})
    with pytest.raises(ValueError, match="çok fazla satır"):
        load_term_list(huge)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "Dosya boş"),
        ([["Terim", "Açıklama"], ["kart", "x"]], "tek sütunlu olmalı; dosyada A, B"),
        ([[None, "Terim"], [None, "kart"]], "A sütununda olmalı; dosyada veri B"),
        ([[None], ["kart"]], "A1 hücresi boş"),
        ([["Terim"], [None]], "altında aranacak terim yok"),
        ([["Terim"], ["x" * 501]], "2. satır çok uzun"),
    ],
)
def test_term_list_rejects_unclear_files(rows: list[list[object]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_term_sheet(rows)


def test_term_list_limit() -> None:
    with pytest.raises(ValueError, match="en fazla"):
        parse_term_sheet([["Terim"], *([f"t{i}"] for i in range(MAX_TERMS + 1))])


def _code(data: bytes) -> Rejection:
    with pytest.raises(TermListRejected) as refused:
        load_term_list(data)
    return refused.value.code


def test_the_row_limit_is_2001_rows_on_every_sheet() -> None:
    header = [["Terim"]]
    full = header + [[f"t{i % 150}"] for i in range(2000)]
    assert len(load_term_list(sheet_bytes(("Liste", full))).terms) == 150
    blank_beyond = full + [[None]] * 30
    assert len(load_term_list(sheet_bytes(("Liste", blank_beyond))).terms) == 150
    assert _code(sheet_bytes(("Liste", [*full, ["fazla"]]))) is Rejection.TOO_MANY_ROWS
    second = sheet_bytes(("Liste", header + [["kart"]]), ("Ek", [["x"]] * 2002))
    assert _code(second) is Rejection.TOO_MANY_ROWS


def test_beyond_the_50th_column_nothing_is_read() -> None:
    wide = sheet_bytes(("Liste", [[None] * 50 + ["Terim"], [None] * 50 + ["kart"]]))
    with pytest.raises(TermListRejected, match="Dosya boş") as refused:
        load_term_list(wide)
    assert refused.value.code is Rejection.LAYOUT_INVALID
    within = sheet_bytes(("Liste", [["Terim"] + [None] * 48 + ["x"], ["kart"]]))
    with pytest.raises(TermListRejected, match="dosyada A, AX sütunlarında"):
        load_term_list(within)


def test_codes_of_unreadable_and_oversized_files(tmp_path: Path) -> None:
    assert _code(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 512) is Rejection.NOT_XLSX  # .xls
    assert _code(b"Terim\nkart\n") is Rejection.NOT_XLSX  # .csv
    bomb = BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("xl/sheet.xml", b"0" * (101 * 1024 * 1024))
    with pytest.raises(TermListRejected, match="100 MB") as refused:
        load_term_list(bomb.getvalue())
    assert refused.value.code is Rejection.TOO_LARGE_UNPACKED
    assert _code(sheet_bytes(("Liste", [["Terim"], ["x" * 501]]))) is Rejection.TERM_TOO_LONG
    many = sheet_bytes(("Liste", [["Terim"], *([f"t{i}"] for i in range(201))]))
    assert _code(many) is Rejection.TOO_MANY_TERMS
    assert _code(sheet_bytes(("Liste", [["Terim", "x"]]))) is Rejection.LAYOUT_INVALID


def test_number_cells_read_as_numbers_and_a_formula_is_never_run() -> None:
    data = sheet_bytes(("Liste", [["Terim"], [5.0], [12], ["=1+1"], ["kart"]]))
    read = load_term_list(data)
    # the formula has no saved value in a file openpyxl wrote: it reads as a blank row
    assert read.terms == ["5", "12", "kart"] and read.notes == ["1 boş satır atlandı."]
