"""Requests and responses of the search settings and search index endpoints (search-settings).

``values`` of ``PATCH /search-settings`` is read as plain JSON and checked against the settings
schema by the service, so every refused key yields the source's Turkish message (Requirement 3).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

SettingValue = bool | int | float


class SearchSettingField(BaseModel):
    key: str
    label: str
    help: str
    type: Literal["bool", "int", "float"]
    format: Literal["pct"] | None
    min: int | float | None
    max: int | float | None
    step: int | float | None
    effect: Literal["immediate", "reindex"]
    advanced: bool


class SearchSettingSection(BaseModel):
    id: str
    page: Literal["search", "data"]
    title: str
    intro: str
    advanced: bool
    fields: list[SearchSettingField]


class SearchSettings(BaseModel):
    sections: list[SearchSettingSection]
    values: dict[str, SettingValue]
    defaults: dict[str, SettingValue]


class SearchSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any]


class IndexChange(BaseModel):
    trigger: Literal["startup", "dictionary", "terms", "stopwords", "settings", "manual"]
    at: datetime


class SearchIndexState(BaseModel):
    """``GET /search-index`` (Requirement 15); no error text and no content."""

    state: Literal["building", "ready", "stale"]
    stale_inputs: list[Literal["dictionary", "terms", "stopwords", "settings"]]
    columns: int
    objects: int
    dictionary_version: str
    built_at: datetime | None
    build_ms: int | None
    trigger: Literal["startup", "dictionary", "terms", "stopwords", "settings", "manual"] | None
    running: IndexChange | None
    last_failure: IndexChange | None


class SearchSettingsSaved(BaseModel):
    changed: list[str]
    values: dict[str, SettingValue]
    elapsed_ms: int
    index: SearchIndexState


class SearchIndexRebuilt(SearchIndexState):
    elapsed_ms: int
