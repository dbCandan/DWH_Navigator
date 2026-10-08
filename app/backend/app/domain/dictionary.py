"""Dictionary versions and their import (data-dictionary/PRDs/001-dictionary-management).

The application has at most one active dictionary version and keeps the records of one previous
version (the source's ``.bak``); an older version is pruned: its records are deleted and its
version row stays soft-deleted. A dictionary changes only through an import of a workbook in the
template, from the admin screen (``arayuz``) or from the backend script (``betik``).
"""

from enum import StrEnum


class DictionaryStatus(StrEnum):
    ACTIVE = "active"
    PREVIOUS = "previous"
    PRUNED = "pruned"


class ImportChannel(StrEnum):
    SCREEN = "arayuz"
    SCRIPT = "betik"


# Requirement 6: the import answer, the stored version and the status endpoint carry this many
# warnings; the count is kept in full.
MAX_KEPT_WARNINGS = 20
# Requirement 2: the stored source name of the imported workbook.
SOURCE_NAME_MAX_LENGTH = 255
DEFAULT_SOURCE_NAME = "sozluk.xlsx"
# Requirement 2 and Decision 7: the dictionary's own sheet limits.
MAX_DICTIONARY_COLUMNS = 100

DICTIONARY_EMPTY_MESSAGE = "Sözlük henüz içe aktarılmadı."
IMPORT_IN_PROGRESS_MESSAGE = "Başka bir sözlük içe aktarması sürüyor; bitince yeniden deneyin."
FILE_EMPTY_MESSAGE = "Dosya boş"
UNPACKED_TOO_LARGE_MESSAGE = "Dosya açıldığında çok büyük (en fazla 100 MB)."


def too_many_columns_message(sheet: str) -> str:
    return f"“{sheet}” sayfasında en fazla {MAX_DICTIONARY_COLUMNS} sütun olabilir."


def missing_template_column_message(sheet: str, field: str) -> str:
    return f"“{sheet}” sayfasında şablondaki “{field}” sütunu yok; bu alan boş aktarıldı."
