"""A word list to Excel and back (vocabulary-management Requirement 6 and 7).

The format is the source's ``words_to_workbook`` / ``words_from_workbook``: one sheet named
``Terimler`` or ``DurakKelimeler``, a bold header row, one item per row, a term's equivalents in
one cell joined with ", ". Reading takes the named sheet, or the first sheet when it is missing or
empty, through the shared safe reader with the list's own limits (5,001 rows, 20 columns).
Headers are matched after Turkish folding without spaces; an all-empty row is skipped; an
equivalents cell splits at commas, semicolons, vertical bars and line ends.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.domain.turkish_text import fold
from app.domain.vocabulary import MAX_LIST_ITEMS, VocabularyList, VocabularyRejected
from app.infrastructure.excel.reader import (
    TooManyRows,
    WorkbookTooLarge,
    WorkbookUnreadable,
    open_workbook,
)
from app.infrastructure.excel.writer import formulas_as_text, workbook_bytes
from app.services.analysis.loader import _cell

# kind -> (sheet title, ((key, header, header aliases), ...)), the source's WORD_SHEETS.
WORD_SHEETS: dict[VocabularyList, tuple[str, tuple[tuple[str, str, tuple[str, ...]], ...]]] = {
    VocabularyList.TERMS: ("Terimler", (
        ("term", "Terim", ("terim", "term")),
        ("equivalents", "Eşdeğerler", ("esdegerler", "esdeger", "equivalents")),
        ("domain", "Alan", ("alan", "domain")),
        ("note", "Not", ("not", "note", "aciklama")),
    )),
    VocabularyList.STOPWORDS: ("DurakKelimeler", (
        ("word", "Kelime", ("kelime", "word", "durakkelime")),
        ("group", "Grup", ("grup", "group")),
    )),
}  # fmt: skip
_EQUIVALENT_SPLIT = re.compile(r"[,;|\n]")
_REQUIRED_KEYS = ("term", "equivalents", "word")
_COLUMN_WIDTHS = {
    "Terim": 28,
    "Eşdeğerler": 70,
    "Alan": 16,
    "Not": 50,
    "Kelime": 24,
    "Grup": 24,
}
MAX_SHEET_COLUMNS = 20
FILENAME_PREFIXES = {
    VocabularyList.TERMS: "TerimSozlugu",
    VocabularyList.STOPWORDS: "DurakKelimeler",
}


def _unreadable(
    message: str = "Dosya Excel (.xlsx) olarak okunamadı.",
) -> VocabularyRejected:
    return VocabularyRejected("vocabulary_workbook_unreadable", message)


def _sheet_rows(data: bytes, title: str) -> list[list[object]]:
    try:
        with open_workbook(data) as book:
            names = book.sheet_names
            rows = (
                book.rows(title, max_rows=MAX_LIST_ITEMS + 1, max_cols=MAX_SHEET_COLUMNS)
                if title in names
                else []
            )
            if not rows and names:
                rows = book.rows(names[0], max_rows=MAX_LIST_ITEMS + 1, max_cols=MAX_SHEET_COLUMNS)
            return rows
    except TooManyRows:
        raise VocabularyRejected(
            "vocabulary_workbook_too_many_rows",
            f"Dosyada çok fazla satır var (en fazla {MAX_LIST_ITEMS}).",
        ) from None
    except WorkbookTooLarge:
        raise _unreadable("Dosya açıldığında çok büyük (en fazla 100 MB).") from None
    except WorkbookUnreadable:
        raise _unreadable() from None


def items_from_workbook(kind: VocabularyList, data: bytes) -> list[dict[str, Any]]:
    """A word list exported to Excel (and maybe edited) back as items for the list checks."""

    title, fields = WORD_SHEETS[kind]
    rows = _sheet_rows(data, title)
    header = {fold(_cell(h)).replace(" ", ""): i for i, h in enumerate(rows[0] if rows else [])}
    where: dict[str, int] = {}
    for key, name, aliases in fields:
        column = next((header[a] for a in aliases if a in header), None)
        if column is not None:
            where[key] = column
        elif key in _REQUIRED_KEYS:
            raise VocabularyRejected(
                "vocabulary_workbook_column_missing",
                f"“{name}” sütunu bulunamadı; dışa aktarılan dosyanın başlıklarını "
                f"koruyun ({', '.join(f[1] for f in fields)}).",
            )
    out: list[dict[str, Any]] = []
    for row in rows[1:]:
        item: dict[str, Any] = {k: _cell(row[i]) if i < len(row) else "" for k, i in where.items()}
        if not any(item.values()):
            continue
        if kind is VocabularyList.TERMS:
            parts = _EQUIVALENT_SPLIT.split(str(item.get("equivalents", "")))
            item["equivalents"] = [p.strip() for p in parts if p.strip()]
        out.append(item)
    if not out:
        raise VocabularyRejected("vocabulary_workbook_empty", f"“{title}” sayfasında kayıt yok.")
    return out


def items_to_workbook(kind: VocabularyList, items: Sequence[Mapping[str, Any]]) -> bytes:
    """One word list as a one-sheet workbook that ``items_from_workbook`` reads back."""

    title, fields = WORD_SHEETS[kind]
    book = Workbook()
    book.remove(book.worksheets[0])
    sheet = book.create_sheet(title)
    sheet.append([name for _, name, _ in fields])
    for item in items:
        sheet.append(
            [
                ", ".join(v) if isinstance(v := item.get(key), list) else (v or None)
                for key, _, _ in fields
            ]
        )
    formulas_as_text(sheet)
    for row in sheet.iter_rows(max_row=1):
        for cell in row:
            cell.font = Font(bold=True)
    for i, (_, name, _) in enumerate(fields, 1):
        sheet.column_dimensions[get_column_letter(i)].width = _COLUMN_WIDTHS.get(name, 20)
    sheet.freeze_panes = "A2"
    return workbook_bytes(book)
