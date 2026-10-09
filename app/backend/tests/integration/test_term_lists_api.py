"""Term lists over HTTP, PostgreSQL, the real analysis jobs and a real-TCP fake model server
(data-dictionary 005-list-search Requirement 2-16; Acceptance 4).

The source's ``test_term_list_end_to_end`` and ``test_term_list_rejects_bad_files`` through the new
endpoints, the owner-only visibility, the one running list of the tenant, the listing and the
newest five per person, the term's analysis record, saved answers, the term's answer and reports
after a dictionary re-import, votes on a term, and no term or file name in the logs.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook

from app.api import excel_transfer
from app.infrastructure.excel.writer import XLSX_MEDIA_TYPE
from tests.fakes.telemetry import TelemetryCapture
from tests.integration.analysis import Qa, qa_harness
from tests.integration.conftest import RecordingHandler, SignedIn
from tests.integration.data_dictionary import DataDictionary, error, sql
from tests.parity import excel_dump
from tests.unit.analysis.workbooks import SAMPLE_OBJECTS, SAMPLE_ROWS, xlsx_bytes

pytestmark = pytest.mark.integration

TERM = "kart limit doluluk"  # the fake analyst suggests tables for it
OTHER = "uzay gemisi yakıtı"
FINAL = ("completed", "cancelled", "interrupted")


def xlsx(cells: list[Any]) -> bytes:
    book = Workbook()
    ws = book.active
    assert ws is not None
    for value in cells:
        ws.append([value])
    out = BytesIO()
    book.save(out)
    return out.getvalue()


@pytest.fixture
async def qa(dd: DataDictionary) -> AsyncIterator[Qa]:
    async for each in qa_harness(dd):
        each.model.per_question = {}
        yield each


async def upload(
    qa: Qa,
    data: bytes,
    who: SignedIn | None = None,
    name: str = "terimler.xlsx",
    media_type: str = XLSX_MEDIA_TYPE,
) -> Any:
    return await qa.request(
        "POST",
        "/term-lists",
        who,
        content=data,
        headers={"Content-Type": media_type, "X-Filename": name},
    )


async def finished(qa: Qa, list_id: str, who: SignedIn | None = None) -> dict[str, Any]:
    async with asyncio.timeout(60):
        while True:
            response = await qa.request("GET", f"/term-lists/{list_id}", who)
            assert response.status_code == 200, response.text
            body: dict[str, Any] = response.json()
            if body["status"] in FINAL:
                return body
            await asyncio.sleep(0.05)


async def run_list(qa: Qa, cells: list[Any], who: SignedIn | None = None, **kw: Any) -> Any:
    response = await upload(qa, xlsx(cells), who, **kw)
    assert response.status_code == 201, response.text
    return await finished(qa, response.json()["id"], who)


async def test_term_list_end_to_end(qa: Qa) -> None:
    """Upload a one-column list, follow its progress, read a term, get both reports."""
    response = await upload(qa, xlsx(["Terim", TERM, "", OTHER, "Kart limit doluluk"]))
    assert response.status_code == 201, response.text
    started = response.json()
    assert [i["term"] for i in started["items"]] == [TERM, OTHER]
    assert started["status"] == "running" and started["owner"]["public_id"] == qa.user.public_id
    assert started["dictionary_version"] == qa.dd.index.engine().dictionary.version
    job = await finished(qa, started["id"])
    assert job["status"] == "completed" and job["done"] == 2 and job["total"] == 2
    assert [i["state"] for i in job["items"]] == ["answered", "answered"]
    assert job["header"] == "Terim" and len(job["notes"]) == 2  # a blank row and a repeat
    assert job["eta_ms"] is None and job["finished_at"] is not None
    first = job["items"][0]
    assert first["flow"] == "analyst" and first["best"] is not None and first["elapsed_ms"] > 0
    item = await qa.request("GET", f"/term-lists/{job['id']}/items/1")
    assert item.status_code == 200 and item.json()["query"] == TERM
    assert item.json()["objects"][0]["key"] == first["best"]["key"]
    report = await qa.request("GET", f"/term-lists/{job['id']}/report")
    assert report.status_code == 200 and report.content[:2] == b"PK"
    assert report.headers["content-disposition"].startswith(
        'attachment; filename="VSA_liste_terimler_'
    )
    book = load_workbook(BytesIO(report.content))
    assert book.sheetnames == ["Özet", "Öneriler"]
    assert book["Özet"]["B3"].value == "terimler.xlsx"
    term_report = await qa.request("GET", f"/term-lists/{job['id']}/items/1/report")
    assert term_report.status_code == 200
    assert 'filename="VSA_ask_kart_limit_doluluk_' in term_report.headers["content-disposition"]
    assert error(await qa.request("GET", "/term-lists/yok")) == (404, "term_list_not_found")
    records = await sql(
        "SELECT origin, list_public_id, list_file_name, list_position, query FROM "
        "analysis_record ORDER BY list_position"
    )
    assert [tuple(r) for r in records] == [
        ("list", job["id"], "terimler.xlsx", 1, TERM),
        ("list", job["id"], "terimler.xlsx", 2, OTHER),
    ]


async def test_term_list_rejects_bad_files(
    qa: Qa, telemetry_capture: TelemetryCapture, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = await upload(qa, b"not an excel file")
    assert error(bad) == (422, "term_list_not_xlsx")
    assert "Excel (.xlsx) olarak okunamadı" in bad.json()["detail"]["message"]
    empty = await upload(qa, xlsx(["Terim"]))
    assert error(empty) == (422, "term_list_layout_invalid")
    assert "aranacak terim yok" in empty.json()["detail"]["message"]
    many = await upload(qa, xlsx(["Terim", *[f"t{i}" for i in range(201)]]))
    assert error(many) == (422, "term_list_too_many_terms")
    long_term = await upload(qa, xlsx(["Terim", "x" * 501]))
    assert error(long_term) == (422, "term_list_term_too_long")
    assert error(await upload(qa, xlsx(["Terim", TERM]), media_type="text/csv")) == (
        415,
        "unsupported_media_type",
    )
    monkeypatch.setattr(excel_transfer, "MAX_UPLOAD_BYTES", 100)
    too_large = await upload(qa, xlsx(["Terim", TERM]))
    assert error(too_large) == (413, "upload_too_large")
    monkeypatch.undo()
    assert await sql("SELECT count(*) FROM term_list") == [(0,)]
    reasons = {
        labels["reason"]: value
        for labels, value in telemetry_capture.points(
            "dwhnavigator_term_list_uploads_rejected_total"
        )
    }
    assert reasons["term_list_not_xlsx"] == 1 and reasons["unsupported_media_type"] == 1


async def test_a_list_is_its_owners_alone(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    response = await upload(qa, xlsx(["Terim", TERM, OTHER]))
    list_id = response.json()["id"]
    manager = qa.dd.manager
    for who in (qa.other, manager):
        for method, path in (
            ("GET", f"/term-lists/{list_id}"),
            ("GET", f"/term-lists/{list_id}/items/1"),
            ("GET", f"/term-lists/{list_id}/items/1/report"),
            ("GET", f"/term-lists/{list_id}/report"),
            ("POST", f"/term-lists/{list_id}/cancel"),
            ("POST", f"/term-lists/{list_id}/resume"),
        ):
            assert error(await qa.request(method, path, who)) == (404, "term_list_not_found")
        listed = await qa.request("GET", "/term-lists", who)
        assert listed.json()["items"] == []
    refused = await upload(qa, xlsx(["Terim", TERM]), qa.other)
    assert error(refused) == (409, "term_list_running")
    assert refused.json()["detail"]["message"] == (
        "Başka bir kullanıcının listesi çalışıyor; bitince yeniden deneyin."
    )
    own = await upload(qa, xlsx(["Terim", TERM]))
    assert own.json()["detail"]["message"] == (
        "Bir liste zaten çalışıyor; bitmesini bekleyin ya da durdurun."
    )
    assert error(await qa.request("GET", f"/term-lists/{list_id}/items/1")) == (
        404,
        "term_list_item_not_answered",
    )
    qa.model.hold.set()
    await finished(qa, list_id)


async def test_two_uploads_at_once_start_one_list(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    first, second = await asyncio.gather(
        upload(qa, xlsx(["Terim", TERM])), upload(qa, xlsx(["Terim", OTHER]), qa.other)
    )
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    assert await sql("SELECT count(*) FROM term_list WHERE status = 'running'") == [(1,)]
    qa.model.hold.set()


async def test_stop_and_resume_over_http(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    response = await upload(qa, xlsx(["Terim", TERM, OTHER, "müşteri yaşı"]))
    list_id = response.json()["id"]
    async with asyncio.timeout(10):
        await qa.model.chat_started.wait()
    stopped = await qa.request("POST", f"/term-lists/{list_id}/cancel")
    assert stopped.status_code == 200
    body = stopped.json()
    assert body["stop_requested"] is True and body["status"] == "cancelled"
    assert [i["state"] for i in body["items"]] == ["stopped", "stopped", "stopped"]
    again = await qa.request("POST", f"/term-lists/{list_id}/cancel")
    assert again.json()["status"] == "cancelled"
    qa.model.hold = None
    resumed = await qa.request("POST", f"/term-lists/{list_id}/resume")
    assert resumed.status_code == 200 and resumed.json()["status"] == "running"
    assert resumed.json()["stop_requested"] is False
    done = await finished(qa, list_id)
    assert done["status"] == "completed" and done["done"] == 3
    nothing = await qa.request("POST", f"/term-lists/{list_id}/resume")
    assert error(nothing) == (409, "term_list_nothing_to_resume")
    assert nothing.json()["detail"]["message"] == (
        "Bu listenin bütün terimleri cevaplandı; devam edecek terim yok."
    )


async def test_the_newest_five_lists_of_a_person_are_kept(qa: Qa) -> None:
    ids = []
    for n in range(6):
        done = await run_list(qa, ["Terim", TERM], name=f"liste{n}.xlsx")
        ids.append(done["id"])
    other = await run_list(qa, ["Terim", TERM], qa.other)
    page = (await qa.request("GET", "/term-lists?page_size=2")).json()
    assert page["total"] == 5 and page["page"] == 1 and page["page_size"] == 2
    assert [i["id"] for i in page["items"]] == ids[:0:-1][:2]
    everything = (await qa.request("GET", "/term-lists?page_size=100")).json()["items"]
    assert [i["id"] for i in everything] == ids[:0:-1]
    assert set(everything[0]) == {
        "id", "name", "owner", "status", "stop_requested", "total", "done", "created_at",
        "finished_at",
    }  # fmt: skip
    assert error(await qa.request("GET", f"/term-lists/{ids[0]}")) == (404, "term_list_not_found")
    records = await sql("SELECT count(*) FROM analysis_record WHERE list_public_id = :p", p=ids[0])
    assert records == [(1,)]  # the deleted list's term analysis stays
    assert (await qa.request("GET", f"/term-lists/{other['id']}", qa.other)).status_code == 200
    assert error(await qa.request("GET", "/term-lists?page=0")) == (422, "invalid_request")
    assert error(await qa.request("GET", "/term-lists?page_size=101")) == (422, "invalid_request")


async def test_a_saved_answer_is_given_again_and_marked(qa: Qa) -> None:
    await run_list(qa, ["Terim", TERM])
    again = await run_list(qa, ["Terim", TERM.upper(), OTHER])
    assert [i["flow"] for i in again["items"]] == ["reused", "analyst"]


async def test_answers_and_reports_outlive_a_dictionary_import(qa: Qa) -> None:
    done = await run_list(qa, ["Terim", TERM])
    best = done["items"][0]["best"]["key"]
    before = await qa.request("GET", f"/term-lists/{done['id']}/report")
    sample = xlsx_bytes({"Kolonlar": SAMPLE_ROWS, "Objeler": SAMPLE_OBJECTS})
    imported = await qa.dd.import_dictionary(sample)
    assert imported.status_code in (200, 201), imported.text
    assert best not in qa.dd.index.engine().objects
    item = await qa.request("GET", f"/term-lists/{done['id']}/items/1")
    assert item.status_code == 200 and item.json()["objects"][0]["key"] == best
    after = await qa.request("GET", f"/term-lists/{done['id']}/report")
    assert after.status_code == 200
    first, second = excel_dump.workbook(before.content), excel_dump.workbook(after.content)
    for sheet in (first, second):  # the report's own time is the only difference
        sheet["content"][0]["cells"] = [c for c in sheet["content"][0]["cells"] if c[0] != "B5"]
    assert first == second
    single = await qa.request("GET", f"/term-lists/{done['id']}/items/1/report")
    assert single.status_code == 200


async def test_votes_shape_the_term_but_not_the_row_or_the_report(qa: Qa) -> None:
    done = await run_list(qa, ["Terim", TERM])
    best = done["items"][0]["best"]
    before = await qa.request("GET", f"/term-lists/{done['id']}/report")
    for who in (qa.user, qa.other):
        vote = await qa.request(
            "POST",
            "/votes",
            who,
            json={"query": TERM, "scope": "table", "table_key": best["key"], "vote": "down"},
        )
        assert vote.status_code == 201
    item = (await qa.request("GET", f"/term-lists/{done['id']}/items/1")).json()
    assert [m["key"] for m in item["rejected"]] == [best["key"]]
    assert item["feedback"]["mine"] == {best["key"]: "down"}
    row = (await qa.request("GET", f"/term-lists/{done['id']}")).json()["items"][0]
    assert row["best"] == best
    # A vote on the term is a vote on the same single question, and the other way round.
    single = await qa.finished(await qa.started(TERM, qa.other), qa.other)
    assert [m["key"] for m in single["result"]["rejected"]] == [best["key"]]
    after = await qa.request("GET", f"/term-lists/{done['id']}/report")
    first, second = excel_dump.workbook(before.content), excel_dump.workbook(after.content)
    for sheet in (first, second):
        sheet["content"][0]["cells"] = [c for c in sheet["content"][0]["cells"] if c[0] != "B5"]
    assert first == second


async def test_logs_and_metrics_carry_no_term_or_file_name(
    qa: Qa, recorded_logs: RecordingHandler, telemetry_capture: TelemetryCapture
) -> None:
    marker = "QZXTERIMISARETI"
    done = await run_list(qa, ["Başlık", f"{TERM} {marker}"], name=f"{marker}.xlsx")
    await qa.request("GET", f"/term-lists/{done['id']}/report")
    await qa.request("GET", f"/term-lists/{done['id']}/items/1/report")
    assert [e["event"] for e in recorded_logs.records_of("app.lists")] == [
        "term_list.started",
        "term_list.finished",
        "term_list.report_downloaded",
        "term_list.report_downloaded",
    ]
    finished_event = recorded_logs.events("term_list.finished")[0]
    assert finished_event["status"] == "completed" and finished_event["analyst"] == 1
    assert telemetry_capture.value("dwhnavigator_term_lists_started_total") == 1
    assert (
        telemetry_capture.value("dwhnavigator_term_lists_finished_total", status="completed") == 1
    )
    assert telemetry_capture.value("dwhnavigator_term_list_terms_total", outcome="analyst") == 1
    assert telemetry_capture.value("dwhnavigator_term_list_reports_total", kind="list") == 1
    assert telemetry_capture.value("dwhnavigator_term_list_reports_total", kind="item") == 1
    everything = recorded_logs.rendered() + json.dumps(
        [dict(s.attributes or {}) for s in telemetry_capture.spans()], ensure_ascii=False
    )
    for secret in (marker, TERM, "Başlık"):
        assert secret not in everything, secret


async def test_a_question_waits_for_one_term_at_most(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    response = await upload(qa, xlsx(["Terim", TERM, OTHER, "müşteri yaşı"]))
    list_id = response.json()["id"]
    async with asyncio.timeout(10):
        await qa.model.chat_started.wait()
    question = await qa.started("Müşterinin kredi risk skoru")
    queued = await qa.job(question)
    assert queued["state"] == "queued" and queued["ahead"] == 1  # only the running term
    qa.model.hold.set()
    await qa.finished(question)
    await finished(qa, list_id)
    rows = await sql(
        "SELECT coalesce(list_position, 0), started_at FROM analysis_record ORDER BY started_at"
    )
    assert [r[0] for r in rows] == [1, 0, 2, 3]
