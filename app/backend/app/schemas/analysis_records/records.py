"""Responses of the analysis record endpoints (data-dictionary 008-analysis-records)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

FlowName = Literal["analyst", "reused", "unavailable", "cancelled", "failed", "interrupted"]
PhaseName = Literal[
    "queue", "saved_answer_lookup", "model_check", "rule_hints", "analyst_pick", "analyst_write"
]


class Asker(BaseModel):
    """Who asked: an account (its display name) or a visitor ('<host> · <address>' of the
    moment, 003-anonymous-visitor Requirement 7)."""

    public_id: str
    display_name: str
    kind: Literal["account", "visitor"]


class RecordError(BaseModel):
    code: str
    message: str


class RecordRowOut(BaseModel):
    public_id: str
    asked_at: datetime
    asked_by: Asker
    query: str
    origin: Literal["question", "list"]
    list_public_id: str | None
    list_file_name: str | None
    list_position: int | None
    flow: FlowName
    model: str
    verdict: Literal["VAR", "KISMEN VAR", "BULUNAMADI"] | None
    table_keys: list[str]
    unavailable_reason: str
    error: RecordError | None
    duration_ms: int | None


class RecordPage(BaseModel):
    items: list[RecordRowOut]
    total: int
    page: int
    page_size: int
    snapshot_at: datetime


class PhaseAverage(BaseModel):
    phase: PhaseName
    average_ms: float | None
    count: int


class AskerCount(Asker):
    count: int


class RecordSummary(BaseModel):
    count: int
    newest_at: datetime | None
    with_result: int
    with_tables: int
    flows: dict[FlowName, int]
    analyst_p50_ms: float | None
    analyst_p90_ms: float | None
    p50_ms: float | None
    p90_ms: float | None
    max_ms: float | None
    phases: list[PhaseAverage]
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    askers: list[AskerCount]
    snapshot_at: datetime


class DayCount(BaseModel):
    date: str
    with_tables: int
    without_tables: int


class DailyCounts(BaseModel):
    days: list[DayCount]


class Askers(BaseModel):
    items: list[Asker]


class RecordReuse(BaseModel):
    at: datetime | None
    query: str
    match: Literal["same_question", "same_meaning"]


class RecordStep(BaseModel):
    """One step: no prompt, reply, address or server error text (Requirement 3 and 4)."""

    seq: int
    parent: int | None
    name: str
    kind: Literal["step", "llm", "event"]
    key: str | None
    start_ms: int
    ms: int
    status: Literal["ok", "warn", "error"]
    detail: str
    call: dict[str, Any] | None = None
    check: dict[str, Any] | None = None


class RecordDetail(RecordRowOut):
    summary: str
    reused: RecordReuse | None
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    dictionary_version: str
    started_at: datetime | None
    finished_at: datetime | None
    queue_wait_ms: int | None
    phases: dict[PhaseName, int]
    steps_truncated: bool
    steps: list[RecordStep]


class RecordsDeleted(BaseModel):
    deleted_count: int
    remaining_count: int
