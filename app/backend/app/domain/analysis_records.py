"""Analysis job states, flows and record limits (data-dictionary 004-question-analysis
Requirement 8 and 18, 008-analysis-records Requirement 2 and Decision 12)."""

from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


TERMINAL_STATES = frozenset(
    {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED, JobState.INTERRUPTED}
)


class Flow(StrEnum):
    """Who answered: the source's analist, önbellek, yapılamadı, durduruldu, hata and the new
    yarıda kesildi."""

    ANALYST = "analyst"
    REUSED = "reused"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


COMPLETED_FLOWS = frozenset({Flow.ANALYST, Flow.REUSED, Flow.UNAVAILABLE})


class Origin(StrEnum):
    QUESTION = "question"
    LIST = "list"


class ReusedMatch(StrEnum):
    SAME_QUESTION = "same_question"
    SAME_MEANING = "same_meaning"


# The source's Turkish match words inside the answer (question-analysis Requirement 14).
MATCH_TEXT = {ReusedMatch.SAME_QUESTION: "aynı soru", ReusedMatch.SAME_MEANING: "aynı anlam"}

QUERY_MAX_CHARS = 4000
SUMMARY_MAX_CHARS = 500
REASON_MAX_CHARS = 500
ERROR_CODE_MAX_CHARS = 64
ERROR_MESSAGE_MAX_CHARS = 500
LIST_FILE_NAME_MAX_CHARS = 255
MAX_TABLE_KEYS = 10
SAVED_QUERY_MAX_CHARS = 2000

FAILED_CODE = "analysis_failed"
FAILED_MESSAGE = (
    "Analiz beklenmeyen bir hatayla durdu. Soruyu yeniden sorun; sorun sürerse yöneticinize "
    "bildirin."
)
CANCELLED_CODE = "cancelled"
CANCELLED_MESSAGE = "Kullanıcı durdurdu"
INTERRUPTED_CODE = "interrupted"
INTERRUPTED_MESSAGE = "Analiz yarıda kesildi (uygulama yeniden başladı). Soruyu yeniden sorun."
