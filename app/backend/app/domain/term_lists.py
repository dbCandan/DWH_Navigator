"""Term list states and the codes of a refused list (data-dictionary 005-list-search
Requirement 2-4, 7, 9, 18)."""

from enum import StrEnum


class ListStatus(StrEnum):
    RUNNING = "running"  # sürüyor
    COMPLETED = "completed"  # tamamlandı
    CANCELLED = "cancelled"  # durduruldu
    INTERRUPTED = "interrupted"  # yarıda kesildi


class TermState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    ANSWERED = "answered"
    ERROR = "error"
    STOPPED = "stopped"


class Rejection(StrEnum):
    """Why an uploaded list cannot be read (Requirement 2, 3)."""

    NOT_XLSX = "term_list_not_xlsx"
    TOO_LARGE_UNPACKED = "term_list_too_large_unpacked"
    TOO_MANY_ROWS = "term_list_too_many_rows"
    LAYOUT_INVALID = "term_list_layout_invalid"
    TERM_TOO_LONG = "term_list_term_too_long"
    TOO_MANY_TERMS = "term_list_too_many_terms"


class TermListRejected(ValueError):
    """A list that cannot be read, with its stable code and the source's Turkish message."""

    def __init__(self, code: Rejection, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


KEPT_PER_OWNER = 5
TERM_TOP = 5
TERM_ERROR_CODE = "term_analysis_failed"
TERM_ERROR_MESSAGE = (
    "Bu terim analiz edilirken beklenmeyen bir hata oluştu; listeyi sürdürerek yeniden deneyin."
)
