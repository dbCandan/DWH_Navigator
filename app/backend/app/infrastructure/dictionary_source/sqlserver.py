"""The SQL Server dictionary source (data-dictionary 011-dictionary-sync).

Every statement is a fixed SELECT with an explicit column list, and person and team columns of the
definition tables are never named. The only text built at run time is a catalog query, and the
database name enters it only as the server's QUOTENAME of a name read back from sys.databases.

An access problem is never read as "object missing": a named database that cannot be confirmed, or
whose catalog shows no object (SQL Server hides metadata silently without permission), stops the
read with ``TargetUnavailable`` and produces no exclusion.

pymssql blocks, so it runs in a worker thread and is imported only when first used. Its fixed
timeouts bound that thread; cancelling the awaiting task does not stop it.
"""

import asyncio
import importlib
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from typing import Any

from app.domain.dictionary_source import (
    SourceColumn,
    SourceConnection,
    SourceInvalid,
    SourceProbe,
    SourceSnapshot,
    SourceTable,
    SourceUnavailable,
    TargetUnavailable,
)
from app.infrastructure.dictionary_source.name_matching import (
    DatabaseCatalog,
    match_names,
    reconcile,
)

LOGIN_TIMEOUT_SECONDS = 15  # covers the TCP connection, TLS and the login
QUERY_TIMEOUT_SECONDS = 120
MAX_TABLES = 5_000
MAX_COLUMNS = 200_000
APP_NAME = "dwhnavigator-dictionary-sync"

DEFINITIONS_SQL = "SELECT DatabaseName, SchemaName, ObjectName, Description FROM OPR.DatasetDefinition"
DETAILS_SQL = (
    "SELECT DatabaseName, SchemaName, ObjectName, ColumnName, ColumnDescription, DatasetGroup "
    "FROM OPR.DatasetDefinitionDetail"
)
LAST_CHANGE_SQL = (
    "SELECT (SELECT MAX(TranDate) FROM OPR.DatasetDefinition), "
    "(SELECT MAX(TranDate) FROM OPR.DatasetDefinitionDetail)"
)
DATABASE_NAMES_SQL = "SELECT d.name FROM sys.databases AS d"
DATABASE_STATE_SQL = (
    "SELECT d.name, QUOTENAME(d.name), d.state_desc, HAS_DBACCESS(d.name) "
    "FROM sys.databases AS d WHERE d.name = %s"
)
# The dictionary covers what the warehouse serves: views and stored procedures, never base tables.
CATALOG_OBJECTS_SQL = (
    "SELECT s.name, o.name, o.type FROM {database}.sys.objects AS o "
    "JOIN {database}.sys.schemas AS s ON s.schema_id = o.schema_id "
    "WHERE o.type IN ('V', 'P')"
)
CATALOG_COLUMNS_SQL = (
    "SELECT s.name, o.name, c.name FROM {database}.sys.columns AS c "
    "JOIN {database}.sys.objects AS o ON o.object_id = c.object_id "
    "JOIN {database}.sys.schemas AS s ON s.schema_id = o.schema_id "
    "WHERE o.type = 'V'"
)

# The warehouse layers below the served objects: where load procedures compute their columns.
CODE_LAYERS = ("EDW", "EDWLRY", "EDWSKEY", "EDWUTIL")
MODULES_SQL = (
    "SELECT s.name, o.name, m.definition FROM {database}.sys.sql_modules AS m "
    "JOIN {database}.sys.objects AS o ON o.object_id = m.object_id "
    "JOIN {database}.sys.schemas AS s ON s.schema_id = o.schema_id "
    "WHERE o.type IN ('V', 'P')"
)

_SCHEMA_ERRORS = frozenset({207, 208, 4104})
_LOGIN_ERRORS = frozenset(
    {229, 230, 916, 4060, 4064, 18452, 18456, 18470, 18487, 18488}
)
_TIMEOUT_ERRORS = frozenset({20003})
_CLIENT_ERRORS = range(
    20000, 21000
)  # DB-Library's own numbers; the others come from the server


def _error_parts(error: BaseException) -> tuple[int, str]:
    """pymssql raises with ``(number, message)`` as the arguments or as the single argument."""
    parts: tuple[Any, ...] = error.args
    if len(parts) == 1 and isinstance(parts[0], tuple):
        parts = parts[0]
    number = parts[0] if parts and isinstance(parts[0], int) else 0
    message = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
    if isinstance(message, bytes):
        message = message.decode("utf-8", "replace")
    return number, str(message).casefold()


def _classify(error: BaseException, driver: Any) -> SourceUnavailable | SourceInvalid:
    """The message only selects a class; no part of it leaves this function."""
    number, message = _error_parts(error)
    if number in _SCHEMA_ERRORS or isinstance(error, driver.ProgrammingError):
        return SourceInvalid("schema")
    if number in _LOGIN_ERRORS or "login failed" in message:
        return SourceUnavailable("login")
    if number in _TIMEOUT_ERRORS or "timed out" in message or "timeout" in message:
        return SourceUnavailable("timeout")
    return SourceUnavailable("network")


def _text(value: object) -> str:
    """Trimmed text; the source also stores the word NULL in place of an empty value."""

    text = "" if value is None else str(value).strip()
    return "" if text.casefold() == "null" else text


def _sort_key(row: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return tuple(value.casefold() for value in row), row


def _fetch_rows(
    cursor: Any, key_width: int, limit: int
) -> tuple[list[tuple[str, ...]], int]:
    """Read trimmed rows, count those without a full key, and stop past ``limit`` distinct keys."""
    rows: list[tuple[str, ...]] = []
    keys: set[tuple[str, ...]] = set()
    skipped = 0
    for raw in cursor:
        row = tuple(_text(value) for value in raw)
        key = row[:key_width]
        if not all(key):
            skipped += 1
            continue
        keys.add(tuple(part.casefold() for part in key))
        if len(keys) > limit:
            raise SourceInvalid("limit")
        rows.append(row)
    # The server's row order is not stable; "the first row" of a duplicate must be.
    rows.sort(key=_sort_key)
    return rows, skipped


@dataclass(frozen=True, slots=True)
class _Definitions:
    tables: tuple[SourceTable, ...]
    columns: tuple[SourceColumn, ...]
    skipped: int


@dataclass(frozen=True, slots=True)
class _Targets:
    databases: dict[str, str]  # source spelling -> reachable catalog name
    catalogs: dict[str, DatabaseCatalog]
    missing: tuple[str, ...]
    code: dict[str, str] = field(
        default_factory=dict
    )  # Database.Schema.Name -> definition


def _read_modules(
    cursor: Any, driver: Any, name: str, quoted: str, code: dict[str, str]
) -> None:
    """Definitions are evidence only: a refusal leaves the dictionary update untouched."""

    try:
        cursor.execute(MODULES_SQL.format(database=quoted))
        for schema, object_name, body in cursor:
            if body:
                code[f"{name}.{schema}.{object_name}"] = str(body)
    except driver.Error:
        return


class SqlServerDictionarySource:
    """``DictionarySourcePort`` over pymssql; ``driver`` replaces the module in tests."""

    def __init__(
        self,
        driver: Any | None = None,
        ignored_databases: Collection[str] = (),
        ignored_columns: Collection[str] = (),
        aliases: Mapping[str, str] | None = None,
    ) -> None:
        self._driver = driver
        self._aliases = aliases or {}
        self._ignored = {name.casefold() for name in ignored_databases}
        self._ignored_columns = {name.casefold() for name in ignored_columns}

    async def read(self, connection: SourceConnection) -> SourceSnapshot:
        return await asyncio.to_thread(self._session, connection, self._read)

    async def probe(self, connection: SourceConnection) -> SourceProbe:
        return await asyncio.to_thread(self._session, connection, self._probe)

    def _session[Result](
        self, connection: SourceConnection, work: Callable[[Any, Any], Result]
    ) -> Result:
        driver = self._driver or importlib.import_module("pymssql")
        failure: SourceUnavailable | SourceInvalid
        try:
            link = driver.connect(
                server=connection.host,
                port=str(connection.port),
                user=connection.username,
                password=connection.password,
                database=connection.database,
                login_timeout=LOGIN_TIMEOUT_SECONDS,
                timeout=QUERY_TIMEOUT_SECONDS,
                charset="UTF-8",
                appname=APP_NAME,
                autocommit=True,
                # "off" sends the login unencrypted; "request" still protects it when it can.
                encryption="require" if connection.encrypt else "request",
            )
            try:
                return work(link.cursor(), driver)
            finally:
                link.close()
        except driver.Error as error:
            failure = _classify(error, driver)
        # Raised outside the handler, so the driver's text is not kept as ``__context__``.
        raise failure

    def _read(self, cursor: Any, driver: Any) -> SourceSnapshot:
        definitions = self._in_scope(self._definitions(cursor))
        targets = self._targets(cursor, driver, definitions)
        if targets.missing:
            raise TargetUnavailable(targets.missing)
        snapshot = self._reconciled(definitions, targets)
        code = dict(targets.code)
        for name in self._layers(cursor, set(targets.catalogs)):
            self._modules(cursor, driver, name, code)
        return replace(snapshot, code=code)

    @staticmethod
    def _layers(cursor: Any, targets: set[str]) -> list[str]:
        cursor.execute(DATABASE_NAMES_SQL)
        server = {_text(row[0]).casefold(): _text(row[0]) for row in cursor}
        wanted = {
            server[name.casefold()] for name in CODE_LAYERS if name.casefold() in server
        }
        return sorted(wanted - targets)

    @staticmethod
    def _modules(cursor: Any, driver: Any, name: str, code: dict[str, str]) -> None:
        """A layer's view and procedure text; one that cannot be read only loses its evidence."""

        try:
            cursor.execute(DATABASE_STATE_SQL, (name,))
            rows = list(cursor)
            if len(rows) != 1 or rows[0][2] != "ONLINE" or rows[0][3] != 1:
                return
            server_name, quoted = rows[0][0], rows[0][1]
            if quoted != "[" + str(server_name).replace("]", "]]") + "]":
                return
            _read_modules(cursor, driver, server_name, quoted, code)
        except driver.Error:
            return

    def _probe(self, cursor: Any, driver: Any) -> SourceProbe:
        """Count what ``read`` would return from the databases that can be reached."""
        definitions = self._in_scope(self._definitions(cursor))
        targets = self._targets(cursor, driver, definitions)
        snapshot = self._reconciled(definitions, targets)
        return SourceProbe(
            table_count=len(snapshot.tables),
            column_count=len(snapshot.columns),
            last_change_at=self._last_change(cursor),
            missing_databases=targets.missing,
        )

    def _in_scope(self, definitions: _Definitions) -> _Definitions:
        """Drop the rows of the databases the owner left out of the update."""

        return replace(
            definitions,
            tables=tuple(
                r
                for r in definitions.tables
                if r.database.casefold() not in self._ignored
            ),
            columns=tuple(
                r
                for r in definitions.columns
                if r.database.casefold() not in self._ignored
                and r.name.casefold() not in self._ignored_columns
            ),
        )

    def _reconciled(
        self, definitions: _Definitions, targets: _Targets
    ) -> SourceSnapshot:
        snapshot = reconcile(
            definitions.tables,
            definitions.columns,
            targets.databases,
            targets.catalogs,
            self._aliases,
        )
        return replace(snapshot, skipped=snapshot.skipped + definitions.skipped)

    @staticmethod
    def _definitions(cursor: Any) -> _Definitions:
        cursor.execute(DEFINITIONS_SQL)
        table_rows, table_skips = _fetch_rows(cursor, 3, MAX_TABLES)
        cursor.execute(DETAILS_SQL)
        column_rows, column_skips = _fetch_rows(cursor, 4, MAX_COLUMNS)
        names = {tuple(part.casefold() for part in row[:3]) for row in table_rows}
        names |= {tuple(part.casefold() for part in row[:3]) for row in column_rows}
        if len(names) > MAX_TABLES:
            raise SourceInvalid("limit")
        return _Definitions(
            tables=tuple(SourceTable(*row) for row in table_rows),
            columns=tuple(SourceColumn(*row) for row in column_rows),
            skipped=table_skips + column_skips,
        )

    def _targets(self, cursor: Any, driver: Any, definitions: _Definitions) -> _Targets:
        spellings = {row.database for row in definitions.tables}
        spellings |= {row.database for row in definitions.columns}
        if not spellings:
            return _Targets({}, {}, ())
        cursor.execute(DATABASE_NAMES_SQL)
        server_names = [_text(row[0]) for row in cursor]
        names = match_names(spellings, server_names, exclusive=False)

        missing = {spelling for spelling, name in names.items() if name is None}
        catalogs: dict[str, DatabaseCatalog] = {}
        code: dict[str, str] = {}
        for name in sorted({name for name in names.values() if name is not None}):
            catalog = self._catalog(cursor, driver, name, code)
            if catalog is None:
                missing.add(name)
            else:
                catalogs[name] = catalog
        return _Targets(
            databases={
                spelling: name
                for spelling, name in names.items()
                if name is not None and name in catalogs
            },
            catalogs=catalogs,
            missing=tuple(sorted(missing, key=lambda name: (name.casefold(), name))),
            code=code,
        )

    @staticmethod
    def _catalog(
        cursor: Any, driver: Any, name: str, code: dict[str, str] | None = None
    ) -> DatabaseCatalog | None:
        """Read one catalog; None means the database cannot be trusted, not that it is empty."""
        failure: SourceUnavailable | SourceInvalid
        try:
            cursor.execute(DATABASE_STATE_SQL, (name,))
            rows = list(cursor)
            if len(rows) != 1:
                return None
            server_name, quoted, state, access = rows[0]
            if state != "ONLINE" or access != 1:
                return None
            # QUOTENAME's contract, checked: nothing else may enter the statement text.
            if quoted != "[" + str(server_name).replace("]", "]]") + "]":
                return None

            schemas: dict[str, dict[str, set[str] | None]] = {}
            cursor.execute(CATALOG_OBJECTS_SQL.format(database=quoted))
            for schema, object_name, kind in cursor:
                # A procedure has no column list in the catalog: only the object can be confirmed.
                schemas.setdefault(schema, {})[object_name] = (
                    set() if str(kind).strip() == "V" else None
                )
            if not schemas:
                return None
            cursor.execute(CATALOG_COLUMNS_SQL.format(database=quoted))
            for schema, object_name, column in cursor:
                known = schemas.get(schema, {}).get(object_name)
                if known is not None:
                    known.add(column)
            if code is not None:
                _read_modules(cursor, driver, str(server_name), quoted, code)
            return schemas
        except driver.Error as error:
            number, message = _error_parts(error)
            if (
                number != 0
                and number not in _CLIENT_ERRORS
                and "timed out" not in message
            ):
                return None  # the server refused this database: unreadable
            failure = _classify(error, driver)
        raise failure

    @staticmethod
    def _last_change(cursor: Any) -> datetime | None:
        cursor.execute(LAST_CHANGE_SQL)
        moments = [
            value if isinstance(value, datetime) else datetime.combine(value, time.min)
            for row in cursor
            for value in row
            if isinstance(value, date)
        ]
        return max(moments, default=None)
