"""Responses of the term list endpoints (data-dictionary 005-list-search, API sözleşmesi)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ListStatusName = Literal["running", "completed", "cancelled", "interrupted"]
TermStateName = Literal["queued", "running", "answered", "error", "stopped"]


class ListOwner(BaseModel):
    public_id: str
    display_name: str


class BestTable(BaseModel):
    """The first suggestion as the analysis wrote it (votes do not move it)."""

    key: str
    name: str
    score: float
    level: str


class TermRow(BaseModel):
    position: int
    term: str
    state: TermStateName
    verdict: Literal["VAR", "KISMEN VAR", "BULUNAMADI", ""]
    summary: str
    missing: list[str]
    best: BestTable | None
    flow: Literal["analyst", "reused", "unavailable"] | None
    elapsed_ms: int


class TermListSnapshot(BaseModel):
    """Requirement 7: the list and a row per term (at most 200, not paged)."""

    id: str
    name: str
    owner: ListOwner
    header: str
    notes: list[str]
    status: ListStatusName
    stop_requested: bool
    total: int
    done: int
    elapsed_ms: int
    eta_ms: int | None
    created_at: datetime
    finished_at: datetime | None
    dictionary_version: str
    items: list[TermRow]


class TermListSummary(BaseModel):
    id: str
    name: str
    owner: ListOwner
    status: ListStatusName
    stop_requested: bool
    total: int
    done: int
    created_at: datetime
    finished_at: datetime | None


class TermListPage(BaseModel):
    """Requirement 15: the caller's kept lists, newest first."""

    items: list[TermListSummary]
    page: int
    page_size: int
    total: int
