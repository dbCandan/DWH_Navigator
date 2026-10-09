"""Requests and responses of the word list endpoints (vocabulary-management API sözleşmesi).

The saved list is read as plain JSON and checked by the service, so a list that is not a list
answers the source's ``Liste bekleniyordu`` (``vocabulary_items_invalid``) and a field of the
wrong type answers ``invalid_request`` naming only its place (Requirement 3).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search.settings import SearchIndexState


class TermItem(BaseModel):
    term: str
    equivalents: list[str]
    domain: str
    note: str


class StopwordItem(BaseModel):
    word: str
    group: str


class VocabularyListState(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    list_name: Literal["terms", "stopwords"] = Field(alias="list")
    revision: int
    items: list[TermItem] | list[StopwordItem]


class VocabularyListSaved(VocabularyListState):
    changed: bool
    elapsed_ms: int
    index: SearchIndexState


class VocabularyListSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Any = None
