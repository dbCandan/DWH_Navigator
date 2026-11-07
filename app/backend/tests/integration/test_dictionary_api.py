"""Dictionary versions, export and browsing on PostgreSQL (dictionary-management Acceptance 2).

Requirement 8 (one transaction, the import lock), 9 (build first, then write), 10-11 (the read
function, the empty dictionary), 12 (export), 14 (replaced versions kept), 17, 18 (state, tables, one
table) and the roles of Decision 3; no content in any signal. The Excel import and the empty
template are gone (dictionary-sync Requirement 13): versions come from ``tests.dictionary_seed``.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.core.errors import ApplicationError
from app.db.session import async_session_factory, engine
from app.domain.dictionary import DictionaryStatus
from app.infrastructure.excel.writer import XLSX_MEDIA_TYPE
from app.infrastructure.repositories import dictionary_repository
from app.infrastructure.repositories.dictionary_repository import (
    IMPORT_LOCK_KEY,
    DictionaryRepository,
)
from app.services.analysis.dictionary_workbook import from_workbook, load_dictionary
from app.services.dictionary_reading import read_dictionary
from app.services.search_index import IndexTrigger, SearchIndexBuildFailed
from tests.dictionary_seed import seed_behind_index
from tests.fakes.telemetry import TelemetryCapture
from tests.integration.conftest import RecordingHandler
from tests.integration.data_dictionary import (
    SYNTHETIC_WORKBOOK,
    DataDictionary,
    error,
    first_then,
    sql,
    started_index,
)
from tests.unit.analysis.workbooks import xlsx_bytes

pytestmark = pytest.mark.integration

ISTANBUL = ZoneInfo("Europe/Istanbul")


def workbook(*tables: str, extra: str = "", rows: int = 2) -> bytes:
    """A small dictionary: ``rows`` columns per table, one object row per table."""

    columns = [
        {
            "DatabaseName": "DB",
            "SchemaName": "S",
            "ObjectName": table,
            "ColumnName": f"Kolon{i}{extra}",
            "ColumnDescription": f"{table} açıklaması {i}",
            "Synonyms": "",
            "Role": "",
            "Summary": "",
        }
        for table in tables
        for i in range(rows)
    ]
    objects = [{"ObjectKey": f"DB.S.{t}", "DatasetGroup": f"Grup {t}"} for t in tables]
    objects = [o | {f: "" for f in ("DatabaseName", "SchemaName", "ObjectName")} for o in objects]
    return xlsx_bytes({"Objeler": objects, "Kolonlar": columns})


async def versions() -> list[tuple[str, str, bool]]:
    rows = await sql(
        "SELECT version, status, is_deleted FROM dictionary_version ORDER BY dictionary_version_id"
    )
    return [(str(v), str(s), bool(d)) for v, s, d in rows]


async def record_counts() -> tuple[int, int]:
    (objects,) = (await sql("SELECT count(*) FROM dictionary_object_record"))[0]
    (columns,) = (await sql("SELECT count(*) FROM dictionary_column_record"))[0]
    return int(objects), int(columns)


# --- Decision 3: roles --------------------------------------------------------------------------


async def test_every_endpoint_needs_a_session_and_the_manager_role(dd: DataDictionary) -> None:
    user = await dd.auth.account(dd.admin, "kullanici")
    paths = ["/dictionary", "/dictionary/tables", "/dictionary/tables/DB.S.T", "/dictionary/export"]
    client = dd.auth.client
    for path in paths:
        anonymous = await client.get(
            dd.url(path), headers={dd.auth.settings.tenant_header: dd.manager.tenant_id}
        )
        assert error(anonymous) == (401, "not_authenticated"), path
        assert error(await dd.get(path, user)) == (403, "forbidden"), path
    assert (await dd.get("/dictionary", dd.admin)).status_code == 200
    await sql(
        "UPDATE app_user_role SET role_id = (SELECT role_id FROM app_role WHERE code = "
        "'kullanici') WHERE user_id = (SELECT user_id FROM app_user WHERE public_id = :p)",
        p=dd.manager.public_id,
    )
    assert error(await dd.get("/dictionary")) == (403, "forbidden")  # the service re-reads it


# --- dictionary-sync Requirement 13: no Excel import, no empty template --------------------------


async def test_the_excel_import_and_the_template_are_gone(dd: DataDictionary) -> None:
    upload = {"content": workbook("A"), "headers": {"Content-Type": XLSX_MEDIA_TYPE}}
    for method, path, kwargs in (
        ("POST", "/dictionary/imports", upload),
        ("POST", "/dictionary", upload),
        ("GET", "/dictionary/template", {}),
    ):
        response = await dd.request(method, path, **kwargs)
        assert response.status_code in (404, 405), path
    assert await versions() == []


# --- Requirement 11: no dictionary yet ----------------------------------------------------------


async def test_without_a_dictionary_the_app_runs_empty(dd: DataDictionary) -> None:
    state = (await dd.get("/dictionary")).json()
    assert state == {"active": None, "previous": None, "index_dictionary_version": ""}
    for path in ("/dictionary/tables", "/dictionary/tables/DB.S.T", "/dictionary/export"):
        response = await dd.get(path)
        assert error(response) == (404, "dictionary_not_imported")
        assert response.json()["detail"]["message"] == "Sözlük henüz içe aktarılmadı."
    async with async_session_factory() as session:
        read = await read_dictionary(session, await dd.index.tenant_id())
    assert read.dictionary.columns == [] and read.dictionary.version == ""
    assert read.dictionary.source_path == "dictionary.jsonl"


# --- Requirement 8-10, 12: a written version ------------------------------------------------------


async def test_the_state_shows_a_version_built_then_written(dd: DataDictionary) -> None:
    data = SYNTHETIC_WORKBOOK.read_bytes()
    before = datetime.now(UTC)
    seeded = await dd.seed_dictionary(data, name="sozluk_sentetik.xlsx")
    expected = from_workbook(data)
    assert seeded.written and seeded.version == expected.version
    assert re.fullmatch(r"[0-9a-f]{12}-\d+", seeded.version)

    state = (await dd.get("/dictionary")).json()
    version = state["active"]
    assert version["version"] == expected.version
    assert version["source_name"] == "sozluk_sentetik.xlsx"
    assert version["channel"] == "arayuz"
    assert version["imported_by"] == {
        "public_id": dd.manager.public_id,
        "display_name": "Ayşe Işık",
    }
    assert (version["column_count"], version["object_count"]) == (1557, 87)
    assert version["row_count"] == len(expected.columns)
    assert version["warning_count"] == len(expected.warnings)
    assert version["warnings"] == expected.warnings[:20]
    assert datetime.fromisoformat(version["imported_at"]) >= before
    assert state["previous"] is None
    assert state["index_dictionary_version"] == expected.version
    assert dd.index.engine().dictionary.version == expected.version
    index = (await dd.get("/search-index")).json()
    assert index["state"] == "ready" and index["trigger"] == "dictionary"
    assert (index["columns"], index["objects"]) == (1557, 87)
    assert index["dictionary_version"] == expected.version


async def test_the_database_gives_the_engine_what_the_workbook_gives(dd: DataDictionary) -> None:
    """question-analysis Requirement 3: the stored dictionary reaches the engine unchanged."""

    data = SYNTHETIC_WORKBOOK.read_bytes()
    await dd.seed_dictionary(data)
    imported = from_workbook(data)
    parsed = load_dictionary(imported.objects, imported.columns, imported.version, imported.digest)
    async with async_session_factory() as session:
        read = await read_dictionary(session, await dd.index.tenant_id())
    stored = read.dictionary
    assert stored.columns == parsed.columns
    assert stored.objects == parsed.objects
    assert (stored.version, stored.warnings, stored.source_path) == (
        parsed.version,
        parsed.warnings,
        "dictionary.jsonl",
    )


async def test_the_export_gives_the_active_records_back(dd: DataDictionary) -> None:
    await dd.seed_dictionary(workbook("A", "B"))
    data = workbook("A", "C")
    await dd.seed_dictionary(data)
    exported = await dd.get("/dictionary/export")
    stamp = datetime.now(UTC).astimezone(ISTANBUL)
    disposition = exported.headers["content-disposition"]
    assert re.fullmatch(r'attachment; filename="VeriSozlugu_\d{8}_\d{4}\.xlsx"', disposition)
    assert stamp.strftime("%Y%m%d") in disposition
    assert exported.headers["cache-control"] == "no-store"
    assert from_workbook(exported.content).digest == from_workbook(data).digest


async def test_a_version_written_behind_the_index_leaves_it_stale(dd: DataDictionary) -> None:
    await dd.seed_dictionary(workbook("A"))
    served = dd.index.engine().dictionary.version
    await seed_behind_index(workbook("A", "B"))
    status = (await dd.get("/search-index")).json()
    assert status["state"] == "stale" and status["stale_inputs"] == ["dictionary"]
    assert dd.index.engine().dictionary.version == served


async def test_replaced_versions_keep_their_records(dd: DataDictionary) -> None:
    numbers = []
    for tables in (("A",), ("A", "B"), ("A", "B", "C")):
        numbers.append((await dd.seed_dictionary(workbook(*tables))).version)
    assert await versions() == [
        (numbers[0], "previous", False),
        (numbers[1], "previous", False),
        (numbers[2], "active", False),
    ]
    assert await record_counts() == (1 + 2 + 3, 2 + 4 + 6)
    state = (await dd.get("/dictionary")).json()
    assert state["previous"]["version"] == numbers[1]


async def test_a_write_while_another_one_writes_is_409(dd: DataDictionary) -> None:
    await dd.seed_dictionary(workbook("A"))
    serving = dd.index.serving
    async with engine.connect() as holder:
        await holder.execute(text("BEGIN"))
        await holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": IMPORT_LOCK_KEY})
        with pytest.raises(ApplicationError) as refused:
            await dd.seed_dictionary(workbook("A", "B"))
        await holder.execute(text("ROLLBACK"))
    assert refused.value.status_code == 409
    assert refused.value.code == "dictionary_import_in_progress"
    assert refused.value.message == (
        "Başka bir sözlük içe aktarması sürüyor; bitince yeniden deneyin."
    )
    assert len(await versions()) == 1 and dd.index.serving is serving
    assert dd.index.last_failure is None


async def test_a_failed_build_writes_nothing(dd: DataDictionary) -> None:
    await dd.seed_dictionary(workbook("A"))

    def broken(*_: Any) -> Any:
        raise RuntimeError("kurulamadı")

    dd.use_index(await started_index(builder=first_then(broken)))
    serving = dd.index.serving
    with pytest.raises(SearchIndexBuildFailed):
        await dd.seed_dictionary(workbook("A", "B"))
    assert len(await versions()) == 1 and dd.index.serving is serving
    status = (await dd.get("/search-index")).json()
    assert status["last_failure"]["trigger"] == "dictionary"


async def test_a_write_failing_halfway_leaves_no_trace(
    dd: DataDictionary, monkeypatch: pytest.MonkeyPatch
) -> None:
    await dd.seed_dictionary(workbook("A"))
    before = (await versions(), await record_counts())
    original = dictionary_repository.insert
    calls = {"n": 0}

    def failing_insert(model: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:  # after the object records, before the column records
            raise OSError("disk dolu")
        return original(model)

    monkeypatch.setattr(dictionary_repository, "insert", failing_insert)
    with pytest.raises(SearchIndexBuildFailed):
        await dd.seed_dictionary(workbook("A", "B"))
    assert (await versions(), await record_counts()) == before
    assert dd.index.engine().dictionary.version == before[0][0][0]


# --- Requirement 18: tables and records -----------------------------------------------------


async def test_tables_and_records_as_imported(dd: DataDictionary) -> None:
    columns: list[dict[str, Any]] = [
        {"DatabaseName": "DB", "SchemaName": "S", "ObjectName": n, "ColumnName": c,
         "ColumnDescription": "d", "Notlar": note}
        for n, c, note in (
            ("b", "K1", "x"), ("Z", "K1", ""), ("a/b", "K1", ""), ("b", "K2", ""), ("b", "K1", "tekrar"),
        )
    ]  # fmt: skip
    # An empty row inside the sheet is a record of its own (the source's "..": no names).
    columns.insert(2, {"DatabaseName": "", "SchemaName": "", "ObjectName": "", "ColumnName": "",
                       "ColumnDescription": "", "Notlar": ""})  # fmt: skip
    objects = [{"ObjectKey": "DB.S.b", "Grain": "gün", "DatasetGroup": "G", "BusinessDomain": "Kart",
                "ObjectDescription": "Bir tablo"}]  # fmt: skip
    await dd.seed_dictionary(xlsx_bytes({"Objeler": objects, "Kolonlar": columns}))

    tables = (await dd.get("/dictionary/tables")).json()
    assert [t["key"] for t in tables["items"]] == ["..", "DB.S.Z", "DB.S.a/b", "DB.S.b"]
    assert tables["total"] == 4 and (tables["page"], tables["page_size"]) == (1, 1000)
    assert tables["items"][3] == {
        "key": "DB.S.b",
        "name": "b",
        "group": "G",
        "domain": "Kart",
        "description": "Bir tablo",
        "grain": "gün",
        "columns": 3,
    }
    page = (await dd.get("/dictionary/tables?page=2&page_size=3")).json()
    assert [t["key"] for t in page["items"]] == ["DB.S.b"] and page["total"] == 4
    for bad in ("page=0", "page_size=1001", "page_size=0"):
        assert error(await dd.get(f"/dictionary/tables?{bad}")) == (422, "invalid_request")

    table = (await dd.get("/dictionary/tables/DB.S.b")).json()
    assert table["object"]["ObjectKey"] == "DB.S.b" and table["object"]["Grain"] == "gün"
    assert [(c["ColumnName"], c["Notlar"]) for c in table["columns"]] == [
        ("K1", "x"),
        ("K2", ""),
        ("K1", "tekrar"),
    ]
    slashed = await dd.get("/dictionary/tables/DB.S.a%2Fb")
    assert slashed.status_code == 200 and slashed.json()["object"] is None
    assert (await dd.get("/dictionary/tables/DB.S.a/b")).json()["key"] == "DB.S.a/b"
    assert error(await dd.get("/dictionary/tables/DB.S.yok")) == (
        404,
        "dictionary_table_not_found",
    )


async def test_records_changed_by_hand_get_a_version_of_their_own(
    dd: DataDictionary, recorded_logs: RecordingHandler
) -> None:
    stored = (await dd.seed_dictionary(workbook("A"))).version
    await sql("UPDATE dictionary_column_record SET column_description = 'elle' WHERE position = 0")
    async with async_session_factory() as session:
        read = await read_dictionary(session, await dd.index.tenant_id())
    digest, count = read.dictionary.version.split("-")
    assert read.dictionary.version != stored and count == "2" and len(digest) == 12
    (event,) = recorded_logs.events("dictionary.integrity_mismatch")
    assert event["actual_digest"] == digest and event["stored_digest"] != digest


# --- Gözlemlenebilirlik: no content in any signal -------------------------------------------


async def test_dictionary_content_never_reaches_logs_metrics_or_spans(
    dd: DataDictionary,
    recorded_logs: RecordingHandler,
    telemetry_capture: TelemetryCapture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "GIZLIM9X"
    caplog.set_level(logging.INFO)
    await dd.seed_dictionary(workbook(f"Tablo{marker}", extra=marker), name=f"{marker}.xlsx")
    assert (await dd.get(f"/dictionary/tables/DB.S.Tablo{marker}")).status_code == 200
    assert (await dd.get("/dictionary/export")).status_code == 200

    rendered = recorded_logs.rendered()
    assert marker not in rendered and marker not in caplog.text
    assert marker not in telemetry_capture.everything()
    assert recorded_logs.events("dictionary.export")[0]["kind"] == "dictionary"
    assert "/dictionary/tables/{table_key}" in rendered
    capture = telemetry_capture
    assert capture.value("dwhnavigator_dictionary_exports_total", kind="dictionary") == 1
    assert capture.value("dwhnavigator_dictionary_active_columns") == 2
    assert capture.value("dwhnavigator_dictionary_active_tables") == 1
    assert dd.index.serving is not None and dd.index.serving.trigger is IndexTrigger.DICTIONARY


async def test_the_repository_reads_records_in_the_workbooks_shape(dd: DataDictionary) -> None:
    data = workbook("A", rows=3)
    await dd.seed_dictionary(data)
    imported = from_workbook(data)
    async with async_session_factory() as session:
        repository = DictionaryRepository(session)
        active = await repository.version(await dd.index.tenant_id(), DictionaryStatus.ACTIVE)
        assert active is not None
        assert await repository.objects(active) == imported.objects
        assert await repository.columns(active) == imported.columns
