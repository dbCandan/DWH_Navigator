"""The shared safe Excel reader (data-dictionary/PRDs/001-dictionary-management Requirement 2).

Every uploaded workbook is read here, and only here: the dictionary, the word lists of
vocabulary-management and the term lists of list-search. The workbook stays in memory and never
touches the file system. Before openpyxl opens it, the unpacked size of the ``.xlsx`` package is
added up from its directory and a package that would unpack beyond ``MAX_UNPACKED_BYTES`` is
refused unread; Python's ``zipfile`` stops decompressing a member at its declared size, so the
declared sizes bound what is unpacked. openpyxl reads values only (a formula's saved value, never
its evaluation) and parses the workbook XML with ``defusedxml``; without it the reader refuses to
run. A caller names the sheets it reads and its own row and column limits; of every other sheet
only the name is known.
"""

import math
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from openpyxl.xml import DEFUSEDXML

# The upload limit of every workbook (the HTTP body) and its unpacked limit.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 100 * 1024 * 1024

Rows = list[list[object]]


class WorkbookUnreadable(ValueError):
    """The bytes are not an ``.xlsx`` workbook, or the workbook is damaged."""


class WorkbookTooLarge(ValueError):
    """The package would unpack beyond ``MAX_UNPACKED_BYTES``."""


class TooManyRows(ValueError):
    """A sheet has a filled row beyond the caller's row limit."""


class TooManyColumns(ValueError):
    """The header row of a sheet is filled beyond the caller's column limit."""

    def __init__(self, sheet: str) -> None:
        super().__init__(sheet)
        self.sheet = sheet


def filled(value: object) -> bool:
    """Whether a cell holds a text after trimming (an empty or NaN cell does not)."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return bool(str(value).strip())


def _unpacked_size(data: bytes) -> int:
    try:
        with zipfile.ZipFile(BytesIO(data)) as package:
            return sum(member.file_size for member in package.infolist())
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, OSError) as error:
        raise WorkbookUnreadable from error


class OpenWorkbook:
    """A workbook opened read-only; ``rows`` reads one named sheet within limits."""

    def __init__(self, book: Workbook) -> None:
        self._book = book

    @property
    def sheet_names(self) -> list[str]:
        return list(self._book.sheetnames)

    def rows(
        self,
        name: str,
        *,
        max_rows: int,
        max_cols: int,
        refuse_wider_header: bool = False,
    ) -> Rows:
        """Every row of the sheet as a list of at most ``max_cols`` cell values.

        Rows beyond ``max_rows`` are not kept; a filled one raises ``TooManyRows``. Trailing
        empty rows are dropped. With ``refuse_wider_header`` a header row filled beyond
        ``max_cols`` raises ``TooManyColumns``; otherwise the wider cells are not read.
        """

        sheet = self._book[name]
        width = max_cols + 1 if refuse_wider_header else max_cols
        rows: Rows = []
        try:
            for values in sheet.iter_rows(max_col=width, values_only=True):
                row = list(values)
                if not rows and refuse_wider_header and any(filled(v) for v in row[max_cols:]):
                    raise TooManyColumns(name)
                row = row[:max_cols]
                if len(rows) >= max_rows:
                    if any(filled(v) for v in row):
                        raise TooManyRows(name)
                    continue
                rows.append(row)
        except (TooManyRows, TooManyColumns):
            raise
        except Exception as error:  # a damaged sheet part, an invalid cell value
            raise WorkbookUnreadable from error
        while rows and not any(filled(v) for v in rows[-1]):
            rows.pop()
        return rows


@contextmanager
def open_workbook(data: bytes) -> Iterator[OpenWorkbook]:
    """Open uploaded workbook bytes in memory, after the unpacked-size check."""

    if not DEFUSEDXML:  # pragma: no cover - the admitted lock installs defusedxml
        raise RuntimeError("defusedxml is required to read uploaded workbooks")
    if _unpacked_size(data) > MAX_UNPACKED_BYTES:
        raise WorkbookTooLarge
    try:
        book = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as error:  # not a workbook, a damaged one, an old .xls
        raise WorkbookUnreadable from error
    try:
        yield OpenWorkbook(book)
    finally:
        book.close()
