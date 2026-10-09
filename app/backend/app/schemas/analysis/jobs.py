"""Requests and responses of the question analysis endpoints (data-dictionary
004-question-analysis, API sözleşmesi)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    StrictInt,
    StrictStr,
)

from app.schemas.votes.votes import Tally

JobStateName = Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
StepKey = Literal[
    "saved_answer_lookup",
    "queue",
    "model_check",
    "rule_hints",
    "shortlist",
    "family_search",
    "analyst_report",
]
VerdictName = Literal["VAR", "KISMEN VAR", "BULUNAMADI"]


class AnalysisStart(BaseModel):
    """Requirement 4: the question, how many tables to suggest and whether to analyse anew."""

    model_config = ConfigDict(extra="forbid")

    query: StrictStr
    top: Annotated[StrictInt, Field(ge=1, le=10)] = 5
    fresh: StrictBool = False


class AnalysisError(BaseModel):
    code: str
    message: str


class AnswerColumn(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    column: str
    object: str
    description: str
    synonyms: list[str]
    pii: bool
    group: str | None
    role: str
    signals: list[str]
    caveats: list[str]


class AnswerObject(BaseModel):
    """One suggested (or near) table; answer-feedback adds its vote fields to it."""

    model_config = ConfigDict(extra="allow")

    rank: int
    key: str
    database: str
    schema_: str = Field(alias="schema")
    name: str
    groups: list[str]
    score: float
    level: str
    llm: float | None
    components: dict[str, float]
    covered: list[str]
    missing: list[str]
    long_format: list[str]
    dimension: str
    reason: str
    caveat: list[str]
    usage: str
    covers: str
    columns: list[AnswerColumn]
    # answer-feedback Requirement 7: the votes on this table, its confidence before them and
    # whether people's approval brought a near candidate in (absent when no vote was applied).
    votes: Tally | None = None
    score_before: float | None = None
    promoted: bool | None = None


class EndorsedTable(BaseModel):
    """A table people approved for this question that the answer does not hold."""

    model_config = ConfigDict(populate_by_name=True)

    key: str
    name: str
    schema_: str = Field(alias="schema")
    votes: Tally


class AnswerFeedback(BaseModel):
    """answer-feedback Requirement 7: the votes on the whole answer, whether it is rejected, the
    reading user's own last votes (table key, "" for the answer) and when the answer was written."""

    answer: Tally
    answer_rejected: bool
    mine: dict[str, Literal["up", "down"]]
    answer_at: str | None


class AnswerNote(BaseModel):
    scope: str
    title: str
    text: str


class AnswerReuse(BaseModel):
    at: str
    query: str
    match: str


class AnalysisAnswer(BaseModel):
    """Requirement 7: the answer in the source's fields; answer-feedback adds its own."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    query: str
    verdict: VerdictName
    summary: str
    objects: list[AnswerObject]
    near: list[AnswerObject]
    notes: list[AnswerNote]
    concepts: list[str]
    expansion: list[str]
    method: list[str]
    elapsed_ms: int
    dictionary_version: str
    llm_model: str
    analyst: bool
    fallback: str
    interpretation: str
    design: list[str]
    attention: list[str]
    reused: AnswerReuse | None
    missing: list[str]
    # answer-feedback's fields, absent when the votes could not be applied (Requirement 8).
    rejected: list[AnswerObject] | None = None
    endorsed: list[EndorsedTable] | None = None
    feedback: AnswerFeedback | None = None


class AnalysisJob(BaseModel):
    """The job envelope; ``result`` only in ``GET /analyses/{analysis_id}`` of a completed job."""

    analysis_id: str
    state: JobStateName
    origin: Literal["question", "list"]
    query: str
    fresh: bool
    ahead: int | None
    step: StepKey | None
    flow: Literal["analyst", "reused", "unavailable"] | None
    error: AnalysisError | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AnalysisJobWithResult(AnalysisJob):
    result: AnalysisAnswer | None = None


class ActiveAnalysis(BaseModel):
    analysis: AnalysisJob | None


class ModelStateOut(BaseModel):
    state: Literal["ok", "none", "down"]
    model: str
    code: str | None
    reason: str


class StatusOut(BaseModel):
    """Requirement 17."""

    columns: int
    objects: int
    dictionary_version: str
    llm: str
    llm_state: ModelStateOut
    shortlist: int


class SavedAnswerSummaryOut(BaseModel):
    total: int
    usable: int
    newest_at: datetime | None


class SavedAnswersRemoved(BaseModel):
    removed: int


# --- live progress events (the data line of each event) ----------------------------------------


class SnapshotEvent(BaseModel):
    type: Literal["snapshot"]
    analysis_id: str
    state: JobStateName
    ahead: int | None
    step: StepKey | None
    elapsed_ms: int


class QueuedEvent(BaseModel):
    type: Literal["queued"]
    ahead: int


class StartedEvent(BaseModel):
    type: Literal["started"]


class StepEvent(BaseModel):
    type: Literal["step"]
    key: StepKey
    status: Literal["started", "finished", "error"]
    elapsed_ms: int


class CompletedEvent(BaseModel):
    type: Literal["completed"]
    flow: Literal["analyst", "reused", "unavailable"]
    verdict: VerdictName


class FailedEvent(BaseModel):
    type: Literal["failed"]
    code: str
    message: str


class EndedEvent(BaseModel):
    type: Literal["cancelled", "interrupted"]


AnalysisEvent = Annotated[
    SnapshotEvent
    | QueuedEvent
    | StartedEvent
    | StepEvent
    | CompletedEvent
    | FailedEvent
    | EndedEvent,
    Field(discriminator="type"),
]


class AnalysisStreamEvent(RootModel[AnalysisEvent]):
    """The JSON of one event's ``data:`` line on the live progress stream (Requirement 10)."""
