"""Workbooks written for download: in memory, every text a text (CWE-1236).

A cell value that starts with "=" is written as a text, never as a formula, so a dictionary or
word-list text cannot run in the spreadsheet of the person who opens the file.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def formulas_as_text(sheet: Worksheet) -> None:
    """A text starting with "=" stays a text: openpyxl would write it as a formula."""

    for row in sheet.iter_rows():
        for cell in row:
            if cell.data_type == "f":
                cell.data_type = "s"


def workbook_bytes(book: Workbook) -> bytes:
    """The workbook as ``.xlsx`` bytes; nothing is written to the file system."""

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()
