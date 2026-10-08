"""Dictionary import, export and browsing on PostgreSQL (dictionary-management Acceptance 2).

Requirement 2 (upload limits), 7 (same content), 8 (one transaction, the import lock), 9 (build
first, then write), 10-11 (the read function, the empty dictionary), 12 (export), 14 (two versions
kept), 17, 18 (state, tables, one table) and the roles of Decision 3; no content in any signal.
"""

import logging
import re
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.api import excel_transfer
from app.db.session import async_session_factory, engine
from app.domain.dictionary import DictionaryStatus
from app.infrastructure.repositories import dictionary_repository
from app.infrastructure.repositories.dictionary_repository import (
    IMPORT_LOCK_KEY,
    DictionaryRepository,
)
from app.scripts import dictionary as dictionary_script
from app.services.analysis.dictionary_workbook import from_workbook, load_dictionary
from app.services.dictionary_reading import read_dictionary
from app.services.search_index import IndexTrigger
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
    calls = [
        ("GET", "/dictionary", {}),
        ("GET", "/dictionary/tables", {}),
        ("GET", "/dictionary/tables/DB.S.T", {}),
        ("GET", "/dictionary/export", {}),
        ("GET", "/dictionary/template", {}),
        (
            "POST",
            "/dictionary/imports",
            {"content": b"x", "headers": {"Content-Type": "application/octet-stream"}},
        ),
    ]
    client = dd.auth.client
    for method, path, kwargs in calls:
        anonymous = await client.request(
            method,
            dd.url(path),
            headers={dd.auth.settings.tenant_header: dd.manager.tenant_id},
            **{k: v for k, v in kwargs.items() if k != "headers"},
        )
        assert error(anonymous) == (401, "not_authenticated"), path
        refused = await dd.request(method, path, user, **kwargs)
        assert error(refused) == (403, "forbidden"), path
    assert (await dd.get("/dictionary", dd.admin)).status_code == 200
    await sql(
        "UPDATE app_user_role SET role_id = (SELECT role_id FROM app_role WHERE code = "
        "'kullanici') WHERE user_id = (SELECT user_id FROM app_user WHERE public_id = :p)",
        p=dd.manager.public_id,
    )
    assert error(await dd.get("/dictionary")) == (403, "forbidden")  # the service re-reads it


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
    template = await dd.get("/dictionary/template")
    assert template.status_code == 200
    assert template.headers["content-disposition"] == (
        'attachment; filename="VeriSozlugu_sablon.xlsx"'
    )
    assert load_workbook(BytesIO(template.content)).sheetnames == ["Objeler", "Kolonlar"]


# --- Requirement 7-10: an import ------------------------------------------------------------------


async def test_an_import_builds_the_index_then_writes_the_version(dd: DataDictionary) -> None:
    data = SYNTHETIC_WORKBOOK.read_bytes()
    before = datetime.now(UTC)
    response = await dd.import_dictionary(data, name="C:%5Cveri%5Csozluk_sentetik.xlsx")
    assert response.status_code == 201, response.text
    body = response.json()
    expected = from_workbook(data)
    assert body["changed"] is True
    version = body["version"]
    assert version["version"] == expected.version and re.fullmatch(
        r"[0-9a-f]{12}-\d+", version["version"]
    )
    assert version["source_name"] == "sozluk_sentetik.xlsx"
    assert version["channel"] == "arayuz"
    assert version["imported_by"] == {
        "public_id": dd.manager.public_id,
        "display_name": "Ayşe Işık",
    }
    assert (version["column_count"], version["object_count"]) == (1557, 87)
    assert version["row_count"] == len(expected.columns)
    assert version["warning_count"] == len(expected.warnings)
    assert body["warnings"] == expected.warnings[:20]
    assert datetime.fromisoformat(version["imported_at"]) >= before
    index = body["index"]
    assert index["state"] == "ready" and index["trigger"] == "dictionary"
    assert (index["columns"], index["objects"]) == (1557, 87)
    assert index["dictionary_version"] == expected.version

    state = (await dd.get("/dictionary")).json()
    assert state["active"]["public_id"] == version["public_id"]
    assert state["active"]["warnings"] == expected.warnings[:20]
    assert state["previous"] is None
    assert state["index_dictionary_version"] == expected.version
    assert dd.index.engine().dictionary.version == expected.version


async def test_the_database_gives_the_engine_what_the_workbook_gives(dd: DataDictionary) -> None:
    """question-analysis Requirement 3: the stored dictionary reaches the engine unchanged."""

    data = SYNTHETIC_WORKBOOK.read_bytes()
    assert (await dd.import_dictionary(data)).status_code == 201
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


async def test_the_same_content_creates_no_version(dd: DataDictionary) -> None:
    first = await dd.import_dictionary(workbook("A", "B"), name="ilk.xlsx")
    assert first.status_code == 201
    second = await dd.import_dictionary(workbook("A", "C"), name="ikinci.xlsx")
    assert second.status_code == 201
    exported = await dd.get("/dictionary/export")
    stamp = datetime.now(UTC).astimezone(ISTANBUL)
    disposition = exported.headers["content-disposition"]
    assert re.fullmatch(r'attachment; filename="VeriSozlugu_\d{8}_\d{4}\.xlsx"', disposition)
    assert stamp.strftime("%Y%m%d") in disposition
    assert exported.headers["cache-control"] == "no-store"
    builds = dd.index.serving
    again = await dd.import_dictionary(exported.content, name="geri.xlsx")
    assert again.status_code == 200, again.text
    assert again.json()["changed"] is False
    assert again.json()["version"] == second.json()["version"]  # number, name and time kept
    assert dd.index.serving is builds  # the index was built from the active version already
    assert await versions() == [
        (first.json()["version"]["version"], "previous", False),
        (second.json()["version"]["version"], "active", False),
    ]


async def test_the_same_content_rebuilds_a_stale_index(dd: DataDictionary, tmp_path: Path) -> None:
    assert (await dd.import_dictionary(workbook("A"))).status_code == 201
    served = dd.index.engine().dictionary.version
    # The backend script writes another dictionary; the running index does not know it.
    script_import = tmp_path / "betik.xlsx"
    script_import.write_bytes(workbook("A", "B"))
    await dictionary_script.import_dictionary(str(script_import))
    status = (await dd.get("/search-index")).json()
    assert status["state"] == "stale" and status["stale_inputs"] == ["dictionary"]
    assert dd.index.engine().dictionary.version == served
    again = await dd.import_dictionary(script_import.read_bytes())
    assert again.status_code == 200 and again.json()["changed"] is False
    assert again.json()["version"]["channel"] == "betik"
    assert again.json()["version"]["imported_by"] is None
    assert again.json()["index"]["state"] == "ready"
    assert dd.index.engine().dictionary.version == again.json()["version"]["version"]


async def test_two_versions_are_kept_and_older_ones_pruned(
    dd: DataDictionary, recorded_logs: RecordingHandler
) -> None:
    numbers = []
    for tables in (("A",), ("A", "B"), ("A", "B", "C")):
        response = await dd.import_dictionary(workbook(*tables))
        assert response.status_code == 201
        numbers.append(response.json()["version"]["version"])
    assert await versions() == [
        (numbers[0], "pruned", True),
        (numbers[1], "previous", False),
        (numbers[2], "active", False),
    ]
    # Only the two kept versions have records: 2+4 and 3+6.
    assert await record_counts() == (2 + 3, 4 + 6)
    state = (await dd.get("/dictionary")).json()
    assert state["previous"]["version"] == numbers[1]
    assert recorded_logs.events("dictionary.pruned") == [
        {"event": "dictionary.pruned", "version": numbers[0], "objects": 1, "columns": 2}
    ]
    deleted_at, deleted_by = (
        await sql("SELECT deleted_at, deleted_by FROM dictionary_version WHERE status = 'pruned'")
    )[0]
    assert deleted_at is not None and deleted_by is not None


# --- Requirement 2 and 5: refused uploads -----------------------------------------------------


async def test_refused_uploads_change_nothing(
    dd: DataDictionary, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await dd.import_dictionary(workbook("A"))).status_code == 201
    serving = dd.index.serving
    before = (await versions(), await record_counts())

    invalid = await dd.import_dictionary(xlsx_bytes({"Sayfa1": [{"a": 1}]}))
    assert error(invalid) == (422, "dictionary_workbook_invalid")
    assert invalid.json()["detail"]["message"] == (
        "“Kolonlar” sayfası yok (dosyadaki sayfalar: Sayfa1). Şablonu indirip ona göre doldurun."
    )
    unreadable = await dd.import_dictionary(b"not a workbook")
    assert unreadable.json()["detail"]["message"] == "Dosya Excel (.xlsx) olarak okunamadı."
    assert error(await dd.import_dictionary(b"")) == (422, "dictionary_file_empty")
    assert error(await dd.upload("/dictionary/imports", workbook("B"), media_type="text/csv")) == (
        415,
        "unsupported_media_type",
    )
    monkeypatch.setattr(excel_transfer, "MAX_UPLOAD_BYTES", 100)
    too_large = await dd.import_dictionary(workbook("B"))
    assert error(too_large) == (413, "upload_too_large")
    assert too_large.json()["detail"]["message"] == "Dosya çok büyük (en fazla 20 MB)"

    assert (await versions(), await record_counts()) == before
    assert dd.index.serving is serving


async def test_an_import_while_another_one_writes_is_409(dd: DataDictionary) -> None:
    assert (await dd.import_dictionary(workbook("A"))).status_code == 201
    serving = dd.index.serving
    async with engine.connect() as holder:
        await holder.execute(text("BEGIN"))
        await holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": IMPORT_LOCK_KEY})
        response = await dd.import_dictionary(workbook("A", "B"))
        await holder.execute(text("ROLLBACK"))
    assert error(response) == (409, "dictionary_import_in_progress")
    assert response.json()["detail"]["message"] == (
        "Başka bir sözlük içe aktarması sürüyor; bitince yeniden deneyin."
    )
    assert len(await versions()) == 1 and dd.index.serving is serving
    assert dd.index.last_failure is None


async def test_a_failed_build_writes_nothing(dd: DataDictionary) -> None:
    assert (await dd.import_dictionary(workbook("A"))).status_code == 201

    def broken(*_: Any) -> Any:
        raise RuntimeError("kurulamadı")

    dd.use_index(await started_index(builder=first_then(broken)))
    serving = dd.index.serving
    response = await dd.import_dictionary(workbook("A", "B"))
    assert error(response) == (500, "search_index_build_failed")
    assert response.json()["detail"]["message"] == (
        "Arama indeksi kurulamadı; değişiklik kaydedilmedi."
    )
    assert len(await versions()) == 1 and dd.index.serving is serving
    status = (await dd.get("/search-index")).json()
    assert status["last_failure"]["trigger"] == "dictionary"


async def test_a_write_failing_halfway_leaves_no_trace(
    dd: DataDictionary, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await dd.import_dictionary(workbook("A"))).status_code == 201
    before = (await versions(), await record_counts())
    original = dictionary_repository.insert
    calls = {"n": 0}

    def failing_insert(model: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:  # after the object records, before the column records
            raise OSError("disk dolu")
        return original(model)

    monkeypatch.setattr(dictionary_repository, "insert", failing_insert)
    response = await dd.import_dictionary(workbook("A", "B"))
    assert error(response) == (500, "search_index_build_failed")
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
    response = await dd.import_dictionary(xlsx_bytes({"Objeler": objects, "Kolonlar": columns}))
    assert response.status_code == 201, response.text

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
    response = await dd.import_dictionary(workbook("A"))
    stored = response.json()["version"]["version"]
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
    data = workbook(f"Tablo{marker}", extra=marker)
    created = await dd.import_dictionary(data, name=f"{marker}.xlsx")
    assert created.status_code == 201
    assert (await dd.import_dictionary(data, name=f"{marker}.xlsx")).status_code == 200
    invalid = await dd.import_dictionary(
        xlsx_bytes({"Kolonlar": [{f"{marker}Baslik": marker}]}), name=f"{marker}.xlsx"
    )
    assert error(invalid)[0] == 422
    assert (await dd.get(f"/dictionary/tables/DB.S.Tablo{marker}")).status_code == 200
    assert (await dd.get("/dictionary/export")).status_code == 200

    rendered = recorded_logs.rendered()
    assert marker not in rendered and marker not in caplog.text
    assert marker not in telemetry_capture.everything()
    outcomes = [e["outcome"] for e in recorded_logs.events("dictionary.import")]
    assert outcomes == ["created", "unchanged", "invalid"]
    assert recorded_logs.events("dictionary.export")[0]["kind"] == "dictionary"
    assert "/dictionary/tables/{table_key}" in rendered
    capture = telemetry_capture
    imports = "dwhnavigator_dictionary_imports_total"
    assert capture.value(imports, outcome="created", channel="arayuz") == 1
    assert capture.value(imports, outcome="unchanged", channel="arayuz") == 1
    assert capture.value(imports, outcome="invalid", channel="arayuz") == 1
    assert capture.value("dwhnavigator_dictionary_exports_total", kind="dictionary") == 1
    assert capture.value("dwhnavigator_dictionary_active_columns") == 2
    assert capture.value("dwhnavigator_dictionary_active_tables") == 1
    span_outcomes = {
        (span.attributes or {}).get("dwhnavigator.dictionary.outcome")
        for span in capture.spans("dictionary import")
    }
    assert span_outcomes == {"created", "unchanged", "invalid"}
    assert dd.index.serving is not None and dd.index.serving.trigger is IndexTrigger.DICTIONARY


async def test_the_repository_reads_records_in_the_workbooks_shape(dd: DataDictionary) -> None:
    data = workbook("A", rows=3)
    assert (await dd.import_dictionary(data)).status_code == 201
    imported = from_workbook(data)
    async with async_session_factory() as session:
        repository = DictionaryRepository(session)
        active = await repository.version(await dd.index.tenant_id(), DictionaryStatus.ACTIVE)
        assert active is not None
        assert await repository.objects(active) == imported.objects
        assert await repository.columns(active) == imported.columns
