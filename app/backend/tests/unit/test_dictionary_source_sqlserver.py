"""The SQL Server dictionary source over a fake pymssql (011-dictionary-sync)."""

import random
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pytest

from app.domain.dictionary_source import (
    SourceColumn,
    SourceConnection,
    SourceInvalid,
    SourceProbe,
    SourceTable,
    SourceUnavailable,
    TargetUnavailable,
)
from app.infrastructure.dictionary_source import sqlserver
from app.infrastructure.dictionary_source.sqlserver import SqlServerDictionarySource

pytestmark = pytest.mark.unit

SECRET = "s3cret-Passw0rd"
CONNECTION = SourceConnection("dwh-source", 1433, "EDWUTIL", "reader", SECRET, True)


class FakeError(Exception):
    pass


class FakeOperationalError(FakeError):
    pass


class FakeProgrammingError(FakeError):
    pass


class FakeInterfaceError(FakeError):
    pass


@dataclass
class Database:
    objects: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    procedures: set[tuple[str, str]] = field(default_factory=set)
    state: str = "ONLINE"
    access: int = 1
    catalog_error: Exception | None = None


class FakeCursor:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver
        self.rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, *params: Any) -> None:
        self.driver.statements.append((sql, params))
        failure = self.driver.failures.get(sql)
        if failure is not None:
            raise failure
        self.rows = self._answer(sql, params)

    def _answer(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        driver = self.driver
        if sql == sqlserver.DEFINITIONS_SQL:
            return driver.definitions
        if sql == sqlserver.DETAILS_SQL:
            return driver.details
        if sql == sqlserver.LAST_CHANGE_SQL:
            return [driver.last_change]
        if sql == sqlserver.DATABASE_NAMES_SQL:
            return [(name,) for name in driver.databases]
        if sql == sqlserver.DATABASE_STATE_SQL:
            name = params[0][0]
            target = driver.databases.get(name)
            if target is None or target.state == "HIDDEN":
                return []
            quoted = "[" + name.replace("]", "]]") + "]"
            return [(name, driver.quote(quoted), target.state, target.access)]
        if ".sys.sql_modules AS" in sql:
            return []
        match = re.search(r"FROM (\[.*?\])\.sys\.(objects|columns) AS", sql)
        assert match is not None, sql
        assert params == (), "a catalog statement takes no parameters"
        name = match.group(1)[1:-1].replace("]]", "]")
        target = driver.databases[name]
        if target.catalog_error is not None:
            raise target.catalog_error
        if match.group(2) == "objects":
            # sys.objects.type is char(2), so a view comes back padded.
            return [
                (*key, "P " if key in target.procedures else "V ")
                for key in target.objects
            ]
        return [
            (*key, column)
            for key, columns in target.objects.items()
            for column in columns
        ]

    def __iter__(self) -> Any:
        return iter(self.rows)


class FakeLink:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.driver)

    def close(self) -> None:
        self.driver.closed += 1


class FakeDriver:
    Error = FakeError
    OperationalError = FakeOperationalError
    ProgrammingError = FakeProgrammingError
    InterfaceError = FakeInterfaceError

    def __init__(self) -> None:
        self.definitions: list[tuple[Any, ...]] = [
            ("EDWDM", "dbo", "Customer", " Müşteri ")
        ]
        self.details: list[tuple[Any, ...]] = [
            ("EDWDM", "dbo", "Customer", "CustomerId", "Kimlik", "CRM"),
            ("EDWDM", "dbo", "Customer", "FullName", None, None),
        ]
        self.databases = {
            "EDWDM": Database({("dbo", "Customer"): ["CustomerId", "FullName"]}),
        }
        self.last_change: tuple[Any, ...] = (
            datetime.fromisoformat("2026-01-02"),
            date(2026, 3, 4),
        )
        self.failures: dict[str, Exception] = {}
        self.connect_error: Exception | None = None
        self.connect_arguments: dict[str, Any] = {}
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = 0

    def quote(self, quoted: str) -> str:
        return quoted

    def connect(self, **arguments: Any) -> FakeLink:
        self.connect_arguments = arguments
        if self.connect_error is not None:
            raise self.connect_error
        return FakeLink(self)


@pytest.fixture
def driver() -> FakeDriver:
    return FakeDriver()


async def read(driver: FakeDriver) -> Any:
    return await SqlServerDictionarySource(driver).read(CONNECTION)


async def probe(driver: FakeDriver) -> SourceProbe:
    return await SqlServerDictionarySource(driver).probe(CONNECTION)


# --- connection ----------------------------------------------------------------------------------


async def test_connection_arguments(driver: FakeDriver) -> None:
    await read(driver)
    arguments = driver.connect_arguments
    assert arguments["server"] == "dwh-source"
    assert arguments["port"] == "1433"
    assert arguments["database"] == "EDWUTIL"
    assert arguments["login_timeout"] == sqlserver.LOGIN_TIMEOUT_SECONDS
    assert arguments["timeout"] == sqlserver.QUERY_TIMEOUT_SECONDS
    assert arguments["encryption"] == "require"
    assert driver.closed == 1


async def test_encrypt_off_still_requests_tls(driver: FakeDriver) -> None:
    connection = SourceConnection("h", 1433, "d", "u", SECRET, False)
    await SqlServerDictionarySource(driver).read(connection)
    assert driver.connect_arguments["encryption"] == "request"


def test_password_is_not_in_repr() -> None:
    assert SECRET not in repr(CONNECTION)


# --- mapping -------------------------------------------------------------------------------------


async def test_rows_are_mapped_and_trimmed(driver: FakeDriver) -> None:
    snapshot = await read(driver)
    assert snapshot.tables == (SourceTable("EDWDM", "dbo", "Customer", "Müşteri"),)
    assert snapshot.columns == (
        SourceColumn("EDWDM", "dbo", "Customer", "CustomerId", "Kimlik", "CRM"),
        SourceColumn("EDWDM", "dbo", "Customer", "FullName", "", ""),
    )
    assert snapshot.skipped == 0
    assert snapshot.excluded_tables == snapshot.excluded_columns == ()
    assert snapshot.corrected_tables == snapshot.corrected_columns == ()


async def test_trailing_space_is_trimmed_before_matching(driver: FakeDriver) -> None:
    driver.details[0] = ("EDWDM ", " dbo", "Customer ", "CustomerId ", "Kimlik", "CRM")
    snapshot = await read(driver)
    assert [row.name for row in snapshot.columns] == ["CustomerId", "FullName"]
    assert snapshot.corrected_columns == ()


@pytest.mark.parametrize(
    "row",
    [
        (None, "dbo", "Customer", "X", "", ""),
        ("EDWDM", " ", "Customer", "X", "", ""),
        ("EDWDM", "dbo", None, "X", "", ""),
        ("EDWDM", "dbo", "Customer", "  ", "", ""),
    ],
)
async def test_detail_row_without_a_name_is_skipped(
    driver: FakeDriver, row: tuple[Any, ...]
) -> None:
    driver.details.append(row)
    snapshot = await read(driver)
    assert snapshot.skipped == 1
    assert len(snapshot.columns) == 2


async def test_definition_row_without_a_name_is_skipped(driver: FakeDriver) -> None:
    driver.definitions.append(("EDWDM", "", "Other", "x"))
    assert (await read(driver)).skipped == 1


async def test_definition_without_details_is_left_out_and_counted(
    driver: FakeDriver,
) -> None:
    driver.definitions.append(("EDWDM", "dbo", "Empty", "x"))
    driver.databases["EDWDM"].objects[("dbo", "Empty")] = ["Id"]
    snapshot = await read(driver)
    assert [row.name for row in snapshot.tables] == ["Customer"]
    assert snapshot.skipped == 1
    assert snapshot.excluded_tables == ()


async def test_table_with_only_detail_rows_enters(driver: FakeDriver) -> None:
    driver.definitions.clear()
    snapshot = await read(driver)
    assert snapshot.tables == (SourceTable("EDWDM", "dbo", "Customer", ""),)


async def test_duplicates_keep_a_described_row(driver: FakeDriver) -> None:
    driver.details = [
        ("EDWDM", "dbo", "Customer", "FullName", None, "first"),
        ("EDWDM", "dbo", "Customer", "FullName", "Ad", "second"),
        ("EDWDM", "dbo", "Customer", "FullName", "Soyad", "third"),
    ]
    driver.definitions.append(("EDWDM", "dbo", "Customer", ""))
    snapshot = await read(driver)
    assert (snapshot.columns[0].description, snapshot.columns[0].group) == (
        "Ad",
        "second",
    )
    assert snapshot.tables[0].description == "Müşteri"
    assert snapshot.skipped == 3


async def test_result_does_not_depend_on_row_order(driver: FakeDriver) -> None:
    driver.databases["EDWDM"].objects[("dbo", "Zeta")] = ["B", "A"]
    driver.details += [
        ("EDWDM", "dbo", "Zeta", "B", "1", ""),
        ("EDWDM", "dbo", "Zeta", "A", "2", ""),
        ("EDWDM", "dbo", "Zeta", "A", "3", ""),
        ("EDWDM", "dbo", "Zeta", "Gone", "4", ""),
        ("EDWDM", "dbo", "Gone", "A", "5", ""),
    ]
    expected = await read(driver)
    for seed in range(5):
        random.Random(seed).shuffle(driver.details)
        assert await read(driver) == expected
    assert [row.name for row in expected.columns] == [
        "CustomerId",
        "FullName",
        "A",
        "B",
    ]


async def test_typo_corrected_end_to_end(driver: FakeDriver) -> None:
    driver.definitions = [("EDWDM.", "DBO", "Custmer", "Müşteri")]
    driver.details = [
        ("EDWDM.", "DBO", "Custmer", "CustomerId", "", ""),
        ("EDWDM.", "DBO", "Custmer", "FulName", "", ""),
    ]
    snapshot = await read(driver)
    assert snapshot.tables == (SourceTable("EDWDM", "dbo", "Customer", "Müşteri"),)
    assert snapshot.corrected_tables == (("EDWDM..DBO.Custmer", "EDWDM.dbo.Customer"),)
    assert snapshot.corrected_columns == (
        ("EDWDM.dbo.Customer", "FulName", "FullName"),
    )


# --- limits --------------------------------------------------------------------------------------


async def test_table_limit(driver: FakeDriver, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sqlserver, "MAX_TABLES", 1)
    driver.definitions.append(("EDWDM", "dbo", "Other", ""))
    with pytest.raises(SourceInvalid) as caught:
        await read(driver)
    assert caught.value.code == "limit"


async def test_table_limit_counts_detail_only_tables(
    driver: FakeDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sqlserver, "MAX_TABLES", 1)
    driver.details.append(("EDWDM", "dbo", "Other", "Id", "", ""))
    with pytest.raises(SourceInvalid):
        await read(driver)


async def test_column_limit(
    driver: FakeDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sqlserver, "MAX_COLUMNS", 1)
    with pytest.raises(SourceInvalid) as caught:
        await read(driver)
    assert caught.value.code == "limit"


async def test_duplicates_do_not_count_toward_a_limit(
    driver: FakeDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sqlserver, "MAX_COLUMNS", 2)
    driver.details.append(driver.details[0])
    assert len((await read(driver)).columns) == 2


def test_limits_are_the_plans() -> None:
    assert (sqlserver.MAX_TABLES, sqlserver.MAX_COLUMNS) == (5_000, 200_000)


# --- existence check -----------------------------------------------------------------------------


async def test_missing_object_is_excluded(driver: FakeDriver) -> None:
    driver.definitions.append(("EDWDM", "dbo", "Ghost", "x"))
    driver.details.append(("EDWDM", "dbo", "Ghost", "Id", "", ""))
    snapshot = await read(driver)
    assert snapshot.excluded_tables == ("EDWDM.dbo.Ghost",)
    assert snapshot.excluded_columns == ()
    assert all(row.table != "Ghost" for row in snapshot.columns)


async def test_system_or_other_type_object_is_not_seen(driver: FakeDriver) -> None:
    await read(driver)
    catalog = [sql for sql, _ in driver.statements if "FROM [EDWDM].sys.objects" in sql]
    assert catalog and all("o.type IN ('V', 'P')" in sql for sql in catalog)
    columns = [sql for sql, _ in driver.statements if ".sys.columns AS c" in sql]
    assert columns and all("o.type = 'V'" in sql for sql in columns)


async def test_a_procedure_keeps_its_columns_though_the_catalog_lists_none(
    driver: FakeDriver,
) -> None:
    driver.definitions.append(("EDWBridge", "AIS", "rpt_Loyalty", "Rapor"))
    driver.details.append(
        ("EDWBridge", "AIS", "rpt_Loyalty", "Period", "Dönem", "Grup")
    )
    driver.databases["EDWBridge"] = Database(
        {("AIS", "rpt_Loyalty"): []}, procedures={("AIS", "rpt_Loyalty")}
    )
    snapshot = await read(driver)
    assert any(
        row.table == "rpt_Loyalty" and row.name == "Period" for row in snapshot.columns
    )
    assert ("EDWBridge.AIS.rpt_Loyalty", "Period") not in snapshot.excluded_columns


async def test_missing_column_is_excluded(driver: FakeDriver) -> None:
    driver.details.append(("EDWDM", "dbo", "Customer", "Ghost", "", ""))
    snapshot = await read(driver)
    assert snapshot.excluded_columns == (("EDWDM.dbo.Customer", "Ghost"),)
    assert [row.name for row in snapshot.columns] == ["CustomerId", "FullName"]


async def test_object_left_without_columns_is_excluded(driver: FakeDriver) -> None:
    driver.databases["EDWDM"].objects[("dbo", "Bare")] = ["Real"]
    driver.definitions.append(("EDWDM", "dbo", "Bare", "x"))
    driver.details.append(("EDWDM", "dbo", "Bare", "Gone", "", ""))
    snapshot = await read(driver)
    assert snapshot.excluded_tables == ("EDWDM.dbo.Bare",)
    assert snapshot.excluded_columns == ()
    assert [row.name for row in snapshot.tables] == ["Customer"]
    assert all(row.table != "Bare" for row in snapshot.columns)


async def test_matching_ignores_case_and_keeps_the_catalog_spelling(
    driver: FakeDriver,
) -> None:
    driver.details = [("edwdm", "DBO", "CUSTOMER", "customerid", "", "")]
    driver.definitions = []
    snapshot = await read(driver)
    assert snapshot.columns[0].name == "CustomerId"
    assert snapshot.excluded_tables == ()


def add_target(driver: FakeDriver, name: str, target: Database | None = None) -> None:
    driver.details.append((name, "dbo", "T", "C", "", ""))
    if target is not None:
        driver.databases[name] = target


UNAVAILABLE_CASES = {
    "offline": Database({("dbo", "T"): ["C"]}, state="OFFLINE"),
    "restoring": Database({("dbo", "T"): ["C"]}, state="RESTORING"),
    "no access": Database({("dbo", "T"): ["C"]}, access=0),
    "null access": Database({("dbo", "T"): ["C"]}, access=None),  # type: ignore[arg-type]
    "state row hidden": Database({("dbo", "T"): ["C"]}, state="HIDDEN"),
    "empty catalog": Database({}),
    "catalog refused": Database(
        {("dbo", "T"): ["C"]},
        catalog_error=FakeOperationalError((916, b"not able to access the database")),
    ),
    "catalog offline": Database(
        {("dbo", "T"): ["C"]}, catalog_error=FakeOperationalError((942, b"is offline"))
    ),
    "catalog denied": Database(
        {("dbo", "T"): ["C"]},
        catalog_error=FakeProgrammingError(208, b"invalid object"),
    ),
}


@pytest.mark.parametrize("case", UNAVAILABLE_CASES)
async def test_unusable_database_stops_the_read(driver: FakeDriver, case: str) -> None:
    add_target(driver, "ERPDM", UNAVAILABLE_CASES[case])
    with pytest.raises(TargetUnavailable) as caught:
        await read(driver)
    assert caught.value.databases == ("ERPDM",)
    assert caught.value.code == "target"


async def test_absent_database_stops_the_read(driver: FakeDriver) -> None:
    add_target(driver, "ERPDM")
    with pytest.raises(TargetUnavailable) as caught:
        await read(driver)
    assert caught.value.databases == ("ERPDM",)


async def test_database_gets_no_single_edit_correction(driver: FakeDriver) -> None:
    add_target(driver, "EDWDMM")
    with pytest.raises(TargetUnavailable) as caught:
        await read(driver)
    assert caught.value.databases == ("EDWDMM",)


async def test_database_spellings_share_one_check(driver: FakeDriver) -> None:
    driver.details.append(("EDWDM.", "dbo", "Customer", "CustomerId", "", ""))
    snapshot = await read(driver)
    assert len(snapshot.columns) == 2
    checks = [
        sql for sql, _ in driver.statements if sql == sqlserver.DATABASE_STATE_SQL
    ]
    assert len(checks) == 1


async def test_every_unusable_database_is_named(driver: FakeDriver) -> None:
    add_target(driver, "Zeta", Database({}))
    add_target(driver, "ERPDM")
    with pytest.raises(TargetUnavailable) as caught:
        await read(driver)
    assert caught.value.databases == ("ERPDM", "Zeta")


@pytest.mark.parametrize("case", UNAVAILABLE_CASES)
async def test_probe_reports_instead_of_raising(driver: FakeDriver, case: str) -> None:
    add_target(driver, "ERPDM", UNAVAILABLE_CASES[case])
    result = await probe(driver)
    assert result.missing_databases == ("ERPDM",)
    assert (result.table_count, result.column_count) == (1, 2)


async def test_probe_reports_absent_database(driver: FakeDriver) -> None:
    add_target(driver, "ERPDM")
    assert (await probe(driver)).missing_databases == ("ERPDM",)


async def test_probe_counts_and_last_change(driver: FakeDriver) -> None:
    result = await probe(driver)
    assert result == SourceProbe(1, 2, datetime.fromisoformat("2026-03-04"), ())


async def test_probe_without_any_change_date(driver: FakeDriver) -> None:
    driver.last_change = (None, None)
    assert (await probe(driver)).last_change_at is None


async def test_lost_connection_in_a_catalog_is_not_a_target_problem(
    driver: FakeDriver,
) -> None:
    driver.databases["EDWDM"].catalog_error = FakeOperationalError(
        (20006, b"Write to server failed")
    )
    with pytest.raises(SourceUnavailable) as caught:
        await read(driver)
    assert caught.value.code == "network"
    with pytest.raises(SourceUnavailable):
        await probe(driver)


async def test_catalog_timeout_is_not_a_target_problem(driver: FakeDriver) -> None:
    driver.databases["EDWDM"].catalog_error = FakeOperationalError(
        (20003, b"timed out")
    )
    with pytest.raises(SourceUnavailable) as caught:
        await read(driver)
    assert caught.value.code == "timeout"


# --- identifier quoting --------------------------------------------------------------------------

HOSTILE = "x]; DROP DATABASE EDWDM; --"


async def test_hostile_database_name_enters_only_quoted(driver: FakeDriver) -> None:
    driver.databases[HOSTILE] = Database({("dbo", "T"): ["C"]})
    add_target(driver, HOSTILE)
    await read(driver)

    state = [
        params
        for sql, params in driver.statements
        if sql == sqlserver.DATABASE_STATE_SQL
    ]
    assert ((HOSTILE,),) in state
    catalog = [sql for sql, _ in driver.statements if "x]" in sql]
    assert (
        len(catalog) == 3
    )  # objects, columns and the definitions read for code evidence
    for sql in catalog:
        assert "[x]]; DROP DATABASE EDWDM; --].sys." in sql
        assert sql.replace("[x]]; DROP DATABASE EDWDM; --]", "").count("DROP") == 0


async def test_percent_in_a_name_is_not_formatted(driver: FakeDriver) -> None:
    driver.databases["a%sb"] = Database({("dbo", "T"): ["C"]})
    add_target(driver, "a%sb")
    assert len((await read(driver)).tables) == 2


async def test_unexpected_quoted_form_is_refused(
    driver: FakeDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(driver, "quote", lambda _: "[EDWDM]; DROP TABLE x; --")
    with pytest.raises(TargetUnavailable):
        await read(driver)
    assert not any("DROP" in sql for sql, _ in driver.statements)


async def test_source_text_never_reaches_a_statement(driver: FakeDriver) -> None:
    add_target(driver, "x]; DROP")
    with pytest.raises(TargetUnavailable):
        await read(driver)
    assert not any("DROP" in sql for sql, _ in driver.statements)


# --- statements ----------------------------------------------------------------------------------

FORBIDDEN = ("BusinessOwner", "BusinessTeam", "Analyst", "Developer", "UATResponsible")


async def test_statements_name_no_forbidden_column(driver: FakeDriver) -> None:
    await read(driver)
    read_statements = [sql for sql, _ in driver.statements]
    await probe(driver)
    every = [sql for sql, _ in driver.statements]
    constants = [
        value for name, value in vars(sqlserver).items() if name.endswith("_SQL")
    ]
    for sql in every + constants:
        for name in FORBIDDEN:
            assert name.casefold() not in sql.casefold()
        assert "createdate" not in sql.casefold()
        assert "*" not in sql
    assert not any("trandate" in sql.casefold() for sql in read_statements)


async def test_every_statement_only_reads(driver: FakeDriver) -> None:
    await probe(driver)
    await read(driver)
    for sql, _ in driver.statements:
        assert sql.startswith("SELECT ")
        assert not re.search(
            r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC|ALTER|DROP|CREATE)\b", sql
        )


async def test_catalog_statements_touch_only_system_views(driver: FakeDriver) -> None:
    await read(driver)
    for sql, _ in driver.statements:
        if sql not in (sqlserver.DEFINITIONS_SQL, sqlserver.DETAILS_SQL):
            sources = re.findall(r"(?:FROM|JOIN) (\S+)", sql)
            assert sources and all(
                ".sys." in name or name.startswith("sys.") for name in sources
            )


# --- driver errors -------------------------------------------------------------------------------

TEXT = b"Login failed for user reader at dwh-source " + SECRET.encode()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            FakeOperationalError(
                (20009, b"Unable to connect: Connection refused (111)")
            ),
            "network",
        ),
        (
            FakeOperationalError((20009, b"Net-Lib error during Connection timed out")),
            "timeout",
        ),
        (
            FakeOperationalError((20003, b"Adaptive Server connection timed out")),
            "timeout",
        ),
        (FakeOperationalError((18456, TEXT)), "login"),
        (FakeOperationalError((20002, TEXT)), "login"),
        (FakeOperationalError((4060, b"Cannot open database")), "login"),
        (FakeInterfaceError("Connection to the database failed"), "network"),
        (FakeOperationalError(18456, TEXT), "login"),
    ],
)
async def test_connect_errors(driver: FakeDriver, error: Exception, code: str) -> None:
    driver.connect_error = error
    with pytest.raises(SourceUnavailable) as caught:
        await read(driver)
    assert caught.value.code == code


@pytest.mark.parametrize(
    "sql",
    [sqlserver.DEFINITIONS_SQL, sqlserver.DETAILS_SQL],
    ids=["definition", "detail"],
)
@pytest.mark.parametrize("number", [207, 208])
async def test_missing_definition_table_or_column(
    driver: FakeDriver, sql: str, number: int
) -> None:
    driver.failures[sql] = FakeProgrammingError(
        number, b"Invalid name OPR.DatasetDefinition"
    )
    with pytest.raises(SourceInvalid) as caught:
        await read(driver)
    assert caught.value.code == "schema"
    assert driver.closed == 1


async def test_denied_definition_table_is_a_login_class(driver: FakeDriver) -> None:
    driver.failures[sqlserver.DEFINITIONS_SQL] = FakeOperationalError(
        229, b"permission denied"
    )
    with pytest.raises(SourceUnavailable) as caught:
        await read(driver)
    assert caught.value.code == "login"


async def test_query_timeout(driver: FakeDriver) -> None:
    driver.failures[sqlserver.DETAILS_SQL] = FakeOperationalError((20003, b"timed out"))
    with pytest.raises(SourceUnavailable) as caught:
        await read(driver)
    assert caught.value.code == "timeout"


@pytest.mark.parametrize("number", [18456, 208])
async def test_failure_carries_no_server_text(driver: FakeDriver, number: int) -> None:
    failure: Exception = (
        FakeOperationalError((number, TEXT))
        if number == 18456
        else FakeProgrammingError(number, TEXT)
    )
    driver.failures[sqlserver.DEFINITIONS_SQL] = failure
    with pytest.raises((SourceUnavailable, SourceInvalid)) as caught:
        await read(driver)
    error = caught.value
    assert str(error) == error.code
    assert SECRET not in repr(error)
    assert "reader" not in str(error)
    assert error.__context__ is None and error.__cause__ is None


def test_driver_is_imported_lazily() -> None:
    SqlServerDictionarySource()
    assert "pymssql" not in sys.modules


async def test_an_ignored_column_is_left_out_of_every_object(
    driver: FakeDriver,
) -> None:
    source = SqlServerDictionarySource(driver, ignored_columns=("fullname",))
    snapshot = await source.read(CONNECTION)
    assert [column.name for column in snapshot.columns] == ["CustomerId"]
