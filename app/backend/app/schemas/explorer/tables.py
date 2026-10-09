"""Requests and responses of the dictionary explorer (data-dictionary 007-dictionary-explorer,
API sözleşmesi). The fields are the source's ``App.galaxy``, ``App.objects`` and
``App.object_detail``; the content layer's fields appear only on the tables that layer found."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

MatchLayer = Literal["", "ad", "içerik", "kolon adı"]
LevelName = Literal["Yüksek", "Orta", "Düşük"]


class GalaxyTable(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    name: str
    schema_: str = Field(alias="schema")
    group: str
    columns: int


class Galaxy(BaseModel):
    """Requirement 3: every served table in one response."""

    items: list[GalaxyTable]
    total: int


class TableSearch(BaseModel):
    """Requirement 10: the search text in the body, never in the address."""

    model_config = ConfigDict(extra="forbid")

    query: StrictStr


class FoundTable(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    name: str
    schema_: str = Field(alias="schema")
    columns: int
    groups: list[str]
    match: MatchLayer
    score: float | None = None
    level: LevelName | None = None
    matched: list[str] | None = None
    covered: list[str] | None = None
    missing: list[str] | None = None
    signal: str | None = None


class TableSearchResult(BaseModel):
    query: str
    items: list[FoundTable]
    counts: dict[str, int]
    concepts: list[str]
    elapsed_ms: int


class TableColumn(BaseModel):
    key: str
    column: str
    object: str
    description: str
    synonyms: list[str]
    pii: bool
    group: str | None


class TableDetail(BaseModel):
    """Requirement 11: the table's columns in dictionary order and its join keys."""

    model_config = ConfigDict(populate_by_name=True)

    key: str
    name: str
    schema_: str = Field(alias="schema")
    groups: list[str]
    columns: list[TableColumn]
    join_keys: list[str]
