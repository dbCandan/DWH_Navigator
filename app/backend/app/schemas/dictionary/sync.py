"""Bodies of the dictionary update endpoints (011-dictionary-sync plan.md)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceInput(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=512)
    encrypt: bool = False


class Source(BaseModel):
    configured: bool
    host: str
    port: int
    database: str
    username: str
    has_password: bool
    encrypt: bool
    updated_at: datetime | None


class SourceTest(BaseModel):
    ok: bool
    message: str
    table_count: int
    column_count: int
    last_change_at: datetime | None
    missing_databases: list[str] = []


class Person(BaseModel):
    public_id: str
    display_name: str


class Counts(BaseModel):
    tables_added: int = 0
    tables_removed: int = 0
    tables_changed: int = 0
    tables_excluded: int = 0
    tables_corrected: int = 0
    columns_added: int = 0
    columns_removed: int = 0
    columns_changed: int = 0
    columns_excluded: int = 0
    columns_corrected: int = 0
    fields_filled: int = 0
    fields_normalized: int = 0
    fields_empty: int = 0
    model_calls: int = 0
    model_failures: int = 0
    warnings: int = 0


class RunSummary(BaseModel):
    public_id: str
    kind: Literal["guncelleme", "geri_donus"]
    status: Literal[
        "running", "completed", "no_change", "pending_approval", "rejected", "failed", "interrupted"
    ]
    phase: Literal["reading", "comparing", "filling", "indexing", "done"]
    progress_done: int
    progress_total: int
    started_at: datetime
    finished_at: datetime | None
    started_by: Person | None
    previous_version: str
    new_version: str
    model: str
    counts: Counts
    error_code: str
    error_message: str


class Suggestion(BaseModel):
    public_id: str
    kind: Literal["term", "stopword"]
    value: str
    equivalents: list[str]
    note: str
    status: Literal["pending", "applied"]


class RunDetail(RunSummary):
    warnings: list[str]
    suggestions: list[Suggestion]


class RunsPage(BaseModel):
    items: list[RunSummary]
    total: int
    page: int
    page_size: int


class Change(BaseModel):
    kind: str
    table_key: str
    column_name: str
    field: str
    old_value: str
    new_value: str
    origin: str


class ChangesPage(BaseModel):
    items: list[Change]
    total: int
    page: int
    page_size: int


class ApplySuggestions(BaseModel):
    suggestion_ids: list[str] = Field(min_length=1, max_length=500)


class Version(BaseModel):
    public_id: str
    version: str
    status: Literal["active", "previous", "pending"]
    channel: str
    imported_at: datetime
    imported_by: Person | None
    object_count: int
    column_count: int
    run_public_id: str | None
    expires_at: datetime | None
    can_restore: bool


class VersionsPage(BaseModel):
    items: list[Version]
