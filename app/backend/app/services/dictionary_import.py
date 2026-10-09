"""Reading and checking an uploaded dictionary workbook (dictionary-management Requirement 2-7).

The workbook is opened by the shared safe reader with the dictionary's limits: only the Objeler
and Kolonlar sheets are read (of the others only the names), at most 200,000 data rows and 100
columns per sheet, the header row refused when it goes beyond the 100th column. The template's
checks, records, warnings, digest and version are the source's (``from_sheets``); the new warning
for a template field whose column is missing is added after the source's "Objeler sayfası yok"
warning and before every row warning (Requirement 6). Nothing here writes.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.dictionary import (
    MAX_DICTIONARY_COLUMNS,
    UNPACKED_TOO_LARGE_MESSAGE,
    missing_template_column_message,
    too_many_columns_message,
)
from app.infrastructure.excel.reader import (
    TooManyColumns,
    TooManyRows,
    WorkbookTooLarge,
    WorkbookUnreadable,
    open_workbook,
)
from app.services.analysis.dictionary_workbook import (
    COLUMN_FIELDS,
    COLUMNS_SHEET,
    MAX_IMPORT_ROWS,
    OBJECT_FIELDS,
    TEMPLATE_NAME,
    WorkbookImport,
    from_sheets,
    too_many_rows,
    unreadable,
)
from app.services.analysis.loader import OBJECTS_SHEET, _cell, _resolve_columns

TEMPLATE_SHEETS = (OBJECTS_SHEET, COLUMNS_SHEET)
_OBJECT_NAME_FIELDS = ("DatabaseName", "SchemaName", "ObjectName")


class DictionaryWorkbookInvalid(ValueError):
    """The workbook does not fit the template; the message is the source's Turkish text."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class CheckedDictionary:
    imported: WorkbookImport
    row_count: int
    object_extra_headers: list[str]
    column_extra_headers: list[str]


def _header(rows: Sequence[Sequence[object]]) -> list[str]:
    return [text for text in (_cell(value) for value in (rows[0] if rows else [])) if text]


def template_column_warnings(
    sheets: Mapping[str, Sequence[Sequence[object]]],
) -> list[str]:
    """Requirement 6 (new): a sheet that lacks a template field's column gets one warning per
    field. On Objeler, ObjectKey and the DatabaseName/SchemaName/ObjectName triple stand for each
    other, so their warnings come only when both are missing (Decision 5)."""

    warnings: list[str] = []
    if OBJECTS_SHEET in sheets:
        present = set(_header(sheets[OBJECTS_SHEET]))
        missing = [field for field in OBJECT_FIELDS if field not in present]
        key_missing = "ObjectKey" in missing
        triple_missing = any(field in missing for field in _OBJECT_NAME_FIELDS)
        for field in missing:
            if field == "ObjectKey" and not triple_missing:
                continue
            if field in _OBJECT_NAME_FIELDS and not key_missing:
                continue
            warnings.append(missing_template_column_message(OBJECTS_SHEET, field))
    resolved = _resolve_columns(_header(sheets[COLUMNS_SHEET]))
    for logical, field in TEMPLATE_NAME.items():
        if logical not in resolved:
            warnings.append(missing_template_column_message(COLUMNS_SHEET, field))
    return warnings


def _extra_headers(records: Sequence[Mapping[str, str]], fields: Sequence[str]) -> list[str]:
    return [key for key in records[0] if key not in fields] if records else []


def read_dictionary_sheets(data: bytes) -> dict[str, list[list[object]]]:
    """Every sheet name, with the rows of the two template sheets only."""

    try:
        with open_workbook(data) as book:
            return {
                name: (
                    book.rows(
                        name,
                        max_rows=MAX_IMPORT_ROWS + 1,
                        max_cols=MAX_DICTIONARY_COLUMNS,
                        refuse_wider_header=True,
                    )
                    if name in TEMPLATE_SHEETS
                    else []
                )
                for name in book.sheet_names
            }
    except TooManyRows:
        raise DictionaryWorkbookInvalid(str(too_many_rows())) from None
    except TooManyColumns as wide:
        raise DictionaryWorkbookInvalid(too_many_columns_message(wide.sheet)) from None
    except WorkbookTooLarge:
        raise DictionaryWorkbookInvalid(UNPACKED_TOO_LARGE_MESSAGE) from None
    except WorkbookUnreadable:
        raise DictionaryWorkbookInvalid(str(unreadable())) from None


def check_dictionary_workbook(data: bytes) -> CheckedDictionary:
    """Read and check an uploaded workbook; raises ``DictionaryWorkbookInvalid``."""

    sheets = read_dictionary_sheets(data)
    try:
        imported = from_sheets(sheets, data)
    except ValueError as error:
        raise DictionaryWorkbookInvalid(str(error)) from None
    new = template_column_warnings(sheets)
    if new:
        at = 1 if OBJECTS_SHEET not in sheets else 0
        imported.warnings[at:at] = new
    return CheckedDictionary(
        imported=imported,
        row_count=len(imported.columns),
        object_extra_headers=_extra_headers(imported.objects, OBJECT_FIELDS),
        column_extra_headers=_extra_headers(imported.columns, COLUMN_FIELDS),
    )
