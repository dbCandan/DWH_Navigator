"""Dictionary versions and their import (data-dictionary/PRDs/001-dictionary-management).

The application has at most one active dictionary version and keeps replaced versions for a month;
an older version is pruned: its records are deleted and its version row stays soft-deleted. A dictionary changes through a warehouse update (``kaynak``) or a rollback
(``geri_donus``); ``arayuz`` and ``betik`` remain on versions from the earlier Excel import.
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

DICTIONARY_EMPTY_MESSAGE = "Sözlük henüz içe aktarılmadı."
IMPORT_IN_PROGRESS_MESSAGE = "Başka bir sözlük içe aktarması sürüyor; bitince yeniden deneyin."
UNPACKED_TOO_LARGE_MESSAGE = "Dosya açıldığında çok büyük (en fazla 100 MB)."
