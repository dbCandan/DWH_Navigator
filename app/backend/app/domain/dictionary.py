"""Dictionary versions and their import (data-dictionary/PRDs/001-dictionary-management).

The application has at most one active dictionary version and keeps replaced versions for a month;
an older version is pruned: its records are deleted and its version row stays soft-deleted. A
dictionary changes through a warehouse update (``kaynak``), a rollback (``geri_donus``) or an
import of a workbook in the template from the admin screen (``arayuz``); ``betik`` remains on
versions from the earlier script import.
"""

from enum import StrEnum


class DictionaryStatus(StrEnum):
    ACTIVE = "active"
    PREVIOUS = "previous"
    PENDING = "pending"
    PRUNED = "pruned"


class ImportChannel(StrEnum):
    SCREEN = "arayuz"
    SCRIPT = "betik"
    SOURCE = "kaynak"
    ROLLBACK = "geri_donus"


# 011-dictionary-sync: a replaced version keeps its records this long.
VERSION_RETENTION_DAYS = 30
SOURCE_NAME_WAREHOUSE = "EDWUTIL"

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
UNPACKED_TOO_LARGE_MESSAGE = "Dosya açıldığında çok büyük (en fazla 100 MB)."


def too_many_columns_message(sheet: str) -> str:
    return f"“{sheet}” sayfasında en fazla {MAX_DICTIONARY_COLUMNS} sütun olabilir."


def missing_template_column_message(sheet: str, field: str) -> str:
    return f"“{sheet}” sayfasında şablondaki “{field}” sütunu yok; bu alan boş aktarıldı."
