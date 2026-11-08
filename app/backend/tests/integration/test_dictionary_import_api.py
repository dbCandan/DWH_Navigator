"""The dictionary's Excel import and the empty template on PostgreSQL (dictionary-management).

Requirement 2 (upload limits), 5 (the template's messages), 7 (same content), 8 (one transaction,
the import lock), 9 (build first, then write), 15 (the screen's import) and the template download;
no content in any signal. An import replaces the whole dictionary and keeps the replaced version
for a rollback (dictionary-sync Requirement 13); its interplay with a running or waiting update is
in ``test_dictionary_sync_api``.
"""

import logging
import re
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.api import excel_transfer
from app.db.session import engine
from app.infrastructure.repositories import dictionary_repository
from app.infrastructure.repositories.dictionary_repository import IMPORT_LOCK_KEY
from app.services.analysis.dictionary_workbook import from_workbook
from app.services.search_index import IndexTrigger
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
from tests.integration.test_dictionary_api import record_counts, versions, workbook
from tests.unit.analysis.workbooks import xlsx_bytes

pytestmark = pytest.mark.integration


# --- the empty template ---------------------------------------------------------------------------


async def test_the_template_has_the_two_sheets_even_without_a_dictionary(dd: DataDictionary) -> None:
    template = await dd.get("/dictionary/template")
    assert template.status_code == 200
    assert template.headers["content-disposition"] == (
        'attachment; filename="VeriSozlugu_sablon.xlsx"'
    )
    assert template.headers["cache-control"] == "no-store"
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


async def test_an_import_replaces_the_dictionary_and_keeps_the_old_one(dd: DataDictionary) -> None:
    first = await dd.import_dictionary(workbook("A", "B"), name="ilk.xlsx")
    assert first.status_code == 201
    second = await dd.import_dictionary(workbook("C"), name="ikinci.xlsx")
    assert second.status_code == 201
    tables = (await dd.get("/dictionary/tables")).json()
    assert [t["key"] for t in tables["items"]] == ["DB.S.C"]  # replaced, not merged
    assert await versions() == [
        (first.json()["version"]["version"], "previous", False),
        (second.json()["version"]["version"], "active", False),
    ]
    assert await record_counts() == (2 + 1, 4 + 2)  # the replaced version keeps its records
    listed = (await dd.get("/dictionary/versions")).json()
    assert [v["channel"] for v in listed["items"]][:2] == ["arayuz", "arayuz"]


async def test_the_same_content_creates_no_version(dd: DataDictionary) -> None:
    first = await dd.import_dictionary(workbook("A", "B"), name="ilk.xlsx")
    assert first.status_code == 201
    second = await dd.import_dictionary(workbook("A", "C"), name="ikinci.xlsx")
    assert second.status_code == 201
    exported = await dd.get("/dictionary/export")
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


async def test_the_same_content_rebuilds_a_stale_index(dd: DataDictionary) -> None:
    assert (await dd.import_dictionary(workbook("A"))).status_code == 201
    served = dd.index.engine().dictionary.version
    # Another dictionary is written behind the running index.
    data = workbook("A", "B")
    await seed_behind_index(data, name="betik.xlsx")
    status = (await dd.get("/search-index")).json()
    assert status["state"] == "stale" and status["stale_inputs"] == ["dictionary"]
    assert dd.index.engine().dictionary.version == served
    again = await dd.import_dictionary(data)
    assert again.status_code == 200 and again.json()["changed"] is False
    assert again.json()["version"]["channel"] == "betik"
    assert again.json()["version"]["imported_by"] is None
    assert again.json()["index"]["state"] == "ready"
    assert dd.index.engine().dictionary.version == again.json()["version"]["version"]


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
    empty = await dd.import_dictionary(b"")
    assert error(empty) == (422, "dictionary_file_empty")
    assert empty.json()["detail"]["message"] == "Dosya boş"
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


# --- Gözlemlenebilirlik: no content in any signal -------------------------------------------


async def test_an_import_puts_no_content_into_logs_metrics_or_spans(
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
    assert (await dd.get("/dictionary/template")).status_code == 200

    rendered = recorded_logs.rendered()
    assert marker not in rendered and marker not in caplog.text
    assert marker not in telemetry_capture.everything()
    outcomes = [e["outcome"] for e in recorded_logs.events("dictionary.import")]
    assert outcomes == ["created", "unchanged", "invalid"]
    assert recorded_logs.events("dictionary.export")[0]["kind"] == "template"
    capture = telemetry_capture
    imports = "dwhnavigator_dictionary_imports_total"
    assert capture.value(imports, outcome="created", channel="arayuz") == 1
    assert capture.value(imports, outcome="unchanged", channel="arayuz") == 1
    assert capture.value(imports, outcome="invalid", channel="arayuz") == 1
    assert capture.value("dwhnavigator_dictionary_exports_total", kind="template") == 1
    span_outcomes = {
        (span.attributes or {}).get("dwhnavigator.dictionary.outcome")
        for span in capture.spans("dictionary import")
    }
    assert span_outcomes == {"created", "unchanged", "invalid"}
    assert dd.index.serving is not None and dd.index.serving.trigger is IndexTrigger.DICTIONARY
    rows = await sql("SELECT source_name FROM dictionary_version")
    assert rows == [(f"{marker}.xlsx",)]  # the name is stored, never logged
