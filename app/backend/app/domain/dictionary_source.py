"""The dictionary source port and its failure classes (data-dictionary 011-dictionary-sync).

The adapter reads the dictionary definitions and the target catalogs; nothing here writes to the
source. A failure carries a fixed ``code`` and never server text, an address or a credential.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

SourceUnavailableCode = Literal["network", "login", "timeout"]
SourceInvalidCode = Literal["schema", "limit"]


@dataclass(frozen=True, slots=True)
class SourceConnection:
    host: str
    port: int
    database: str
    username: str
    password: str = field(repr=False)
    encrypt: bool


@dataclass(frozen=True, slots=True)
class SourceTable:
    database: str
    schema: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class SourceColumn:
    database: str
    schema: str
    table: str
    name: str
    description: str
    group: str


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    tables: tuple[SourceTable, ...]  # verified objects only
    columns: tuple[SourceColumn, ...]  # verified columns only
    skipped: int  # malformed or duplicate rows
    excluded_tables: tuple[str, ...]  # DB.Schema.Object keys absent from the target
    excluded_columns: tuple[tuple[str, str], ...]  # (table key, column name)
    corrected_tables: tuple[tuple[str, str], ...]  # (source key, catalog key)
    corrected_columns: tuple[tuple[str, str, str], ...]  # (catalog table key, source, catalog name)
    unverified_tables: tuple[str, ...] = ()  # objects whose columns the catalog cannot show
    # database -> schema -> object -> columns (None: a procedure); what the warehouse really has.
    catalogs: Mapping[str, Mapping[str, Mapping[str, Collection[str] | None]]] = field(
        default_factory=dict, repr=False
    )
    # Database.Schema.Name -> view or procedure text of the target and warehouse layers, for
    # following a column through its load code. Empty when no definition could be read.
    code: Mapping[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class SourceProbe:
    table_count: int
    column_count: int
    last_change_at: datetime | None
    missing_databases: tuple[str, ...]  # databases the dictionary names that cannot be reached


class SourceUnavailable(Exception):
    """Network, login or timeout failure; ``code`` is the only detail."""

    def __init__(self, code: SourceUnavailableCode) -> None:
        super().__init__(code)
        self.code: SourceUnavailableCode = code


class SourceInvalid(Exception):
    """The definition tables or columns are missing, or a limit is exceeded."""

    def __init__(self, code: SourceInvalidCode) -> None:
        super().__init__(code)
        self.code: SourceInvalidCode = code


class TargetUnavailable(Exception):
    """A named database is absent, unreadable or shows an empty catalog; never "object missing"."""

    code: Literal["target"] = "target"

    def __init__(self, databases: tuple[str, ...]) -> None:
        super().__init__(self.code)
        self.databases = databases


class DictionarySourcePort(Protocol):
    async def probe(self, connection: SourceConnection) -> SourceProbe: ...

    async def read(self, connection: SourceConnection) -> SourceSnapshot: ...
