"""Responses of the dictionary endpoints (dictionary-management API sözleşmesi).

Records are returned as imported: every template field and every extra column of the sheet,
as texts, in header order.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.search.settings import SearchIndexState


class DictionaryImporter(BaseModel):
    public_id: str
    display_name: str


class DictionaryVersionSummary(BaseModel):
    public_id: str
    version: str
    source_name: str
    imported_at: datetime
    imported_by: DictionaryImporter | None
    channel: Literal["arayuz", "betik"]
    object_count: int
    column_count: int
    row_count: int
    warning_count: int


class ActiveDictionaryVersion(DictionaryVersionSummary):
    warnings: list[str]


class DictionaryState(BaseModel):
    active: ActiveDictionaryVersion | None
    previous: DictionaryVersionSummary | None
    index_dictionary_version: str


class DictionaryTable(BaseModel):
    key: str
    name: str
    group: str
    domain: str
    description: str
    grain: str
    columns: int


class DictionaryTablesPage(BaseModel):
    items: list[DictionaryTable]
    total: int
    page: int
    page_size: int


class DictionaryTableRecords(BaseModel):
    key: str
    object: dict[str, str] | None
    columns: list[dict[str, str]]


class DictionaryImported(BaseModel):
    changed: bool
    version: DictionaryVersionSummary
    warnings: list[str]
    index: SearchIndexState
