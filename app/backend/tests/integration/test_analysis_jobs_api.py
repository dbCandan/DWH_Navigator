"""Question analysis jobs over HTTP, PostgreSQL and a real-TCP fake model server.

data-dictionary/PRDs/004-question-analysis Requirement 3-5, 7-18, 23 (Acceptance 4 and 5).
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

import pytest
from openpyxl import load_workbook

from app.core.errors import ApplicationError
from app.db.session import async_session_factory
from app.services.analysis import answer_cache
from app.services.analysis.answer_record import from_record_form
from app.services.analysis.pipeline import Engine
from app.services.search_index import IndexTrigger, build_engine
from app.services.search_inputs import read_inputs
from tests.integration.analysis import Qa, qa_harness, record, saved_answer_count
from tests.integration.conftest import VISITOR_HOST, visitor_row_id
from tests.integration.data_dictionary import DataDictionary
from tests.integration.data_dictionary import sql as sql_rows
from tests.parity import dump, harness
from tests.parity.driver import GENERATED_AT, read_questions
from tests.parity.fake_model import FakeAnalyst
from tests.parity.run_target import TargetClient

pytestmark = pytest.mark.integration

QUESTION = "kredi kartı limit doluluk oranı"


@pytest.fixture
async def qa(dd: DataDictionary) -> AsyncIterator[Qa]:
    async for each in qa_harness(dd):
        yield each


async def reference_answer(qa: Qa, query: str, top: int = 5) -> dict[str, Any]:
    """The same question through the engine in process with the parity fake analyst."""

    inputs = await read_inputs(async_session_factory, await qa.dd.index.tenant_id())
    engine: Engine = build_engine(inputs, None, IndexTrigger.STARTUP)
    core = FakeAnalyst()
    core.begin(query, "normal")
    result = engine.with_llm(TargetClient(core)).analyze(query, top)
    return dump.answer(answer_cache.encode(result))


async def test_a_question_runs_as_a_job_and_answers_as_the_engine_does(qa: Qa) -> None:
    started = time.monotonic()
    response = await qa.start(QUESTION)
    assert time.monotonic() - started < 2.0
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["state"] == "queued" and body["origin"] == "question"
    assert response.headers["location"].endswith(f"/analyses/{body['analysis_id']}")
    live = await qa.follow(body["analysis_id"])
    assert live.response.headers["content-type"].startswith("text/event-stream")
    assert live.response.headers["cache-control"] == "no-cache"
    assert live.response.headers["x-accel-buffering"] == "no"
    await live.wait_closed(30)
    types = live.types()
    assert types[0] == "snapshot" and types[-1] == "completed"
    assert "started" in types or live.events[0].data["state"] != "queued"
    keys = [e.data["key"] for e in live.events if e.data and e.data["type"] == "step"]
    for key in ("model_check", "rule_hints", "shortlist", "family_search", "analyst_report"):
        assert key in keys
    done = await qa.job(body["analysis_id"])
    assert done["state"] == "completed" and done["flow"] == "analyst"
    result = done["result"]
    assert result["analyst"] is True and result["llm_model"] == "fake-analyst"
    assert set(result) >= {
        "query", "verdict", "summary", "objects", "near", "notes", "concepts", "expansion",
        "method", "elapsed_ms", "dictionary_version", "llm_model", "analyst", "fallback",
        "interpretation", "design", "attention", "reused", "missing",
    }  # fmt: skip
    assert "report_id" not in result
    row = await record(body["analysis_id"])
    assert row["state"] == "completed" and row["flow"] == "analyst"
    assert row["llm_calls"] == 2 and row["prompt_tokens"] == 2400
    assert row["completion_tokens"] == 600
    stored = from_record_form(row["result"])
    assert stored is not None
    expected = await reference_answer(qa, QUESTION)
    assert dump.answer(answer_cache.encode(stored)) == expected
    assert row["phase_analyst_write_ms"] >= 0 and row["steps"]
    calls = [s for s in row["steps"] if s["kind"] == "llm"]
    assert [c["call"]["outcome"] for c in calls] == ["ok", "ok"]
    assert await saved_answer_count() == 1


async def test_the_same_question_again_is_a_saved_answer_and_fresh_analyses_anew(qa: Qa) -> None:
    first = await qa.started(QUESTION)
    await qa.finished(first)
    started = time.monotonic()
    again = await qa.start(QUESTION.upper(), qa.other)  # shared within the tenant
    assert time.monotonic() - started < 2.0
    assert again.status_code == 202
    body = again.json()
    assert body["state"] == "completed" and body["flow"] == "reused"
    reused = await qa.job(body["analysis_id"], qa.other)
    assert reused["result"]["reused"]["match"] == "aynı soru"
    assert reused["result"]["query"] == QUESTION.upper()
    assert reused["result"]["method"][0].startswith("Bu soru ")
    row = await record(body["analysis_id"])
    assert (row["flow"], row["reused_match"], row["model"]) == (
        "reused", "same_question", "fake-analyst"
    )  # fmt: skip
    fresh = await qa.start(QUESTION, fresh=True)
    assert fresh.json()["state"] == "queued" and fresh.json()["fresh"] is True
    done = await qa.finished(fresh.json()["analysis_id"])
    assert done["flow"] == "analyst"
    assert await saved_answer_count() == 1


async def test_the_report_is_made_from_the_record(qa: Qa) -> None:
    analysis_id = await qa.started("=1+1 kart limiti")
    await qa.finished(analysis_id)
    response = await qa.request("GET", f"/analyses/{analysis_id}/report")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="VSA_ask_1_1_kart_limiti_')
    book = load_workbook(BytesIO(response.content))
    assert book.sheetnames == ["Özet", "Öneriler"]
    assert book["Özet"]["B5"].value == "=1+1 kart limiti"
    assert book["Özet"]["B5"].data_type == "s"


async def test_a_job_that_did_not_complete_has_no_report(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    analysis_id = await qa.started(QUESTION)
    response = await qa.request("GET", f"/analyses/{analysis_id}/report")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "analysis_has_no_result"


def snapshot_outputs(question: str, variant: str = "defaults") -> dict[str, str]:
    for line in (harness.SNAPSHOT / "outputs.jsonl").read_text("utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("question") == question and rec.get("variant") == variant:
            outputs: dict[str, str] = rec["outputs"]
            return outputs
    raise AssertionError(question)


async def test_over_http_the_answer_and_keys_are_the_source_snapshots(qa: Qa) -> None:
    """With the parity word lists in PostgreSQL, a job's answer and saved-answer keys have the
    digests the source 76e21a3 wrote for the same question (Requirement 2, Acceptance 2)."""

    items = (await qa.dd.get("/vocabulary/terms")).json()["items"]
    extra = [
        json.loads(line)
        for line in harness.TERMS[1].read_text("utf-8").splitlines()
        if line.strip()
    ]
    saved = await qa.dd.put_list("terms", [*items, *extra])
    assert saved.status_code == 200, saved.text
    questions = {q.id: q.query for q in read_questions(harness.QUESTIONS)}
    for question in ("g-q002", "g-q004", "g-q006"):
        analysis_id = await qa.started(questions[question])
        done = await qa.finished(analysis_id)
        assert done["flow"] == "analyst", question
        row = await record(analysis_id)
        result = from_record_form(row["result"])
        assert result is not None
        result.generated_at = GENERATED_AT
        source = snapshot_outputs(question)
        assert dump.digest(dump.answer(answer_cache.encode(result))) == source["answer"], question
        keys = (
            await sql_rows(
                "SELECT text_key, meaning_key, fingerprint FROM saved_answer "
                "WHERE analysis_public_id = :p",
                p=analysis_id,
            )
        )[0]
        mine = {
            "text_key": keys[0],
            "meaning_key": keys[1],
            "prompts_digest": answer_cache.prompts_digest(),
            "fingerprint": keys[2],
        }
        assert dump.digest(mine) == source["keys"], question


# --- Requirement 4 and 23: the request ---------------------------------------------------------


async def test_the_request_is_checked_with_stable_codes(qa: Qa) -> None:
    cases: list[tuple[Any, int, str]] = [
        ({"query": "   "}, 422, "query_empty"),
        ({"query": "a" * 4001}, 422, "query_too_long"),
        ({"query": "kart\x00limit"}, 422, "query_invalid_characters"),
        ({"query": "kart\x7flimit"}, 422, "query_invalid_characters"),
        ({"query": "kart", "top": 0}, 422, "invalid_request"),
        ({"query": "kart", "top": 11}, 422, "invalid_request"),
        ({"query": "kart", "top": 2.5}, 422, "invalid_request"),
        ({"query": "kart", "top": "3"}, 422, "invalid_request"),
        ({"query": "kart", "fresh": "evet"}, 422, "invalid_request"),
        ({"query": "kart", "ask_id": "x"}, 422, "invalid_request"),
        ({"query": 5}, 422, "invalid_request"),
        ({"query": "x" * 40_000}, 413, "request_too_large"),
    ]
    for body, status_code, code in cases:
        response = await qa.request("POST", "/analyses", json=body)
        assert (response.status_code, response.json()["detail"]["code"]) == (status_code, code)
        assert str(body.get("query", ""))[:20] not in response.text or code == "invalid_request"
    tabs = await qa.start("kart\tlimit\r\nayı ")
    assert tabs.status_code == 202 and tabs.json()["query"] == "kart\tlimit\r\nayı"
    missing = await qa.without_device("POST", "/analyses", json={"query": "kart"})
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "device_id_required"


async def test_starts_are_limited_per_visitor(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    qa.jobs.queue_limit = 200
    codes = [(await qa.start(f"kart {n}")).status_code for n in range(31)]
    assert codes[:30] == [202] * 30
    assert codes[30] == 429
    limited = await qa.start("kart son")
    assert limited.json()["detail"]["code"] == "rate_limited"
    assert (await qa.start("kart başka", qa.other)).status_code == 202


def test_starts_are_limited_per_address(qa: Qa) -> None:
    # 003-anonymous-visitor Requirement 6: 120 starts per address in 60 seconds, whoever asks.
    for n in range(120):
        qa.jobs.check_rate(f"ziyaretci-{n}", "10.1.2.3")
    with pytest.raises(ApplicationError) as refused:
        qa.jobs.check_rate("ziyaretci-yeni", "10.1.2.3")
    assert refused.value.code == "rate_limited"
    qa.jobs.check_rate("ziyaretci-yeni", "10.1.2.4")


async def test_the_record_keeps_the_visitor_its_address_and_host(qa: Qa) -> None:
    analysis_id = await qa.started("kart limiti")
    await qa.finished(analysis_id)
    row = await record(analysis_id)
    assert row["asked_by"] is None
    assert row["asked_by_visitor_id"] == await visitor_row_id(qa.user)
    assert row["client_address"] == "127.0.0.1"
    assert row["client_host"] == VISITOR_HOST


# --- Requirement 8, 9, 11: the queue and stopping ---------------------------------------------


async def test_one_job_runs_at_a_time_in_arrival_order(dd: DataDictionary) -> None:
    # Requirement 9 a: with the limit set to 1, the queue keeps the arrival order.
    async for qa in qa_harness(dd, concurrency=1):
        qa.model.hold = asyncio.Event()
        first = await qa.started("kart limiti")
        async with asyncio.timeout(5):
            await qa.model.chat_started.wait()
        second = await qa.started("mevduat bakiyesi", qa.other)
        third = await qa.started("kredi riski")
        assert (await qa.job(second, qa.other))["ahead"] == 1
        assert (await qa.job(third))["ahead"] == 2
        assert (await qa.job(first))["state"] == "running"
        assert (await qa.job(second, qa.other))["state"] == "queued"
        active = await qa.request("GET", "/analyses/active")
        assert active.json()["analysis"]["analysis_id"] == third
        qa.model.hold.set()
        for job, who in ((first, qa.user), (second, qa.other), (third, qa.user)):
            assert (await qa.finished(job, who))["state"] == "completed"
        assert qa.model.fake.peak == 1
        rows = [await record(job) for job in (first, second, third)]
        starts = [row["started_at"] for row in rows]
        assert starts == sorted(starts)
        assert (await qa.request("GET", "/analyses/active")).json() == {"analysis": None}


async def test_the_queue_limit_refuses_new_questions(dd: DataDictionary) -> None:
    async for qa in qa_harness(dd, queue_limit=1):
        qa.model.hold = asyncio.Event()
        await qa.started("kart limiti")
        async with asyncio.timeout(5):
            await qa.model.chat_started.wait()
        await qa.started("mevduat")
        full = await qa.start("kredi")
        assert (full.status_code, full.json()["detail"]["code"]) == (503, "analysis_queue_full")


async def test_a_queued_job_is_cancelled_at_once(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    running = await qa.started("kart limiti")
    async with asyncio.timeout(5):
        await qa.model.chat_started.wait()
    queued = await qa.started("mevduat")
    stopped = await qa.request("POST", f"/analyses/{queued}/cancel")
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "cancelled"
    assert stopped.json()["error"] == {"code": "cancelled", "message": "Kullanıcı durdurdu"}
    again = await qa.request("POST", f"/analyses/{queued}/cancel")
    assert again.json()["state"] == "cancelled"
    row = await record(queued)
    assert (row["state"], row["flow"], row["error_code"]) == ("cancelled", "cancelled", "cancelled")
    assert any(s["name"] == "Durduruldu" for s in row["steps"])
    assert (await qa.job(running))["state"] == "running"


async def test_a_running_job_closes_the_model_request_and_stops(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    analysis_id = await qa.started("kart limiti")
    live = await qa.follow(analysis_id)
    async with asyncio.timeout(5):
        await qa.model.chat_started.wait()
    closed_before = len(qa.model.fake.closed_at)
    started = time.monotonic()
    stopped = await qa.request("POST", f"/analyses/{analysis_id}/cancel")
    assert time.monotonic() - started < 5.0
    assert stopped.json()["state"] == "cancelled"
    async with asyncio.timeout(2):
        while len(qa.model.fake.closed_at) == closed_before:
            await asyncio.sleep(0.01)
    assert qa.model.fake.closed_at[-1] - started < 2.0
    await live.wait_closed()
    assert live.types()[-1] == "cancelled"
    row = await record(analysis_id)
    assert (row["state"], row["flow"], row["result"]) == ("cancelled", "cancelled", None)
    assert await saved_answer_count() == 0
    assert len(qa.model.chat_requests()) == 1


async def test_another_users_job_is_not_found_anywhere(qa: Qa) -> None:
    analysis_id = await qa.started("kart limiti")
    for method, path in (
        ("GET", f"/analyses/{analysis_id}"),
        ("GET", f"/analyses/{analysis_id}/events"),
        ("POST", f"/analyses/{analysis_id}/cancel"),
        ("GET", f"/analyses/{analysis_id}/report"),
    ):
        response = await qa.request(method, path, qa.other)
        assert (response.status_code, response.json()["detail"]) == (
            404,
            {"code": "analysis_not_found", "message": "Analiz bulunamadı."},
        ), path
        manager = await qa.request(method, path, qa.dd.manager)
        assert manager.status_code == 404, path
    unknown = await qa.request("GET", "/analyses/00000000-0000-0000-0000-000000000000")
    assert unknown.status_code == 404
    await qa.finished(analysis_id)


# --- Requirement 10: the live stream -----------------------------------------------------------


async def test_a_dropped_stream_leaves_the_job_running_and_resumes_from_the_last_event(
    dd: DataDictionary,
) -> None:
    async for qa in qa_harness(dd, keepalive_seconds=0.2):
        qa.model.hold = asyncio.Event()
        analysis_id = await qa.started("kart limiti")
        live = await qa.follow(analysis_id)
        async with asyncio.timeout(5):
            await qa.model.chat_started.wait()
        await live.wait_for("step")
        await asyncio.sleep(0.5)
        assert "canlı" in live.comments()
        seen = [e for e in live.events if e.data is not None]
        first_step = next(e for e in seen if e.data and e.data["type"] == "step")
        await live.response.aclose()
        assert (await qa.job(analysis_id))["state"] == "running"
        again = await qa.follow(analysis_id, last_event_id=first_step.id)
        await again.wait_for("step")
        replay = [e for e in again.events if e.data is not None]
        assert replay[0].data["type"] == "snapshot"
        assert replay[0].data["state"] == "running" and replay[0].data["step"] == "shortlist"
        assert [e.id for e in replay[1:]] == [
            e.id
            for e in seen
            if e.id is not None and e.id > first_step.id and e.data and e.data["type"] == "step"
        ][: len(replay) - 1]
        qa.model.hold.set()
        await again.wait_closed()
        assert again.types()[-1] == "completed"
        late = await qa.follow(analysis_id)
        await late.wait_closed()
        assert late.types() == ["snapshot", "completed"]


async def test_at_most_five_streams_per_user(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    analysis_id = await qa.started("kart limiti")
    streams = [await qa.follow(analysis_id) for _ in range(5)]
    assert all(s.response.status_code == 200 for s in streams)
    sixth = await qa.follow(analysis_id)
    assert sixth.response.status_code == 429
    assert sixth.response.json()["detail"]["code"] == "too_many_streams"
    await streams[0].response.aclose()
    await asyncio.sleep(0.2)
    seventh = await qa.follow(analysis_id)
    assert seventh.response.status_code == 200


async def test_a_stream_ends_when_its_token_expires(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    analysis_id = await qa.started("kart limiti")
    view = await qa.jobs.find(await qa.dd.index.tenant_id(), await qa.visitor_id(), analysis_id)
    chunks = [
        chunk
        async for chunk in qa.jobs.events(view, last_event_id=None, expires_at=time.time() + 0.3)
    ]
    assert chunks[0].startswith("id: ") and '"type":"snapshot"' in chunks[0]
    assert (await qa.job(analysis_id))["state"] in ("queued", "running")


# --- Requirement 12: shutting down and starting again -----------------------------------------


async def test_closing_the_process_interrupts_queued_and_running_jobs(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    running = await qa.started("kart limiti")
    async with asyncio.timeout(5):
        await qa.model.chat_started.wait()
    queued = await qa.started("mevduat")
    live = await qa.follow(running)
    await qa.jobs.shutdown(wait_seconds=5)
    for analysis_id in (running, queued):
        row = await record(analysis_id)
        assert (row["state"], row["flow"], row["error_code"]) == (
            "interrupted", "interrupted", "interrupted"
        )  # fmt: skip
    await live.wait_closed()
    assert live.types()[-1] == "interrupted"
    refused = await qa.start("kredi")
    assert (refused.status_code, refused.json()["detail"]["code"]) == (503, "analysis_unavailable")


async def test_records_left_running_by_an_earlier_process_are_interrupted(qa: Qa) -> None:
    analysis_id = await qa.started("kart limiti")
    await qa.finished(analysis_id)
    await sql_rows(
        "UPDATE analysis_record SET state = 'running', flow = NULL, "
        "asked_at = now() - interval '1 hour' WHERE public_id = :p",
        p=analysis_id,
    )
    assert await qa.jobs.interrupt_leftovers() == 1
    row = await record(analysis_id)
    assert (row["state"], row["flow"]) == ("interrupted", "interrupted")
    assert row["error_message"] == (
        "Analiz yarıda kesildi (uygulama yeniden başladı). Soruyu yeniden sorun."
    )


async def test_no_job_before_the_first_index(qa: Qa) -> None:
    from app.services.search_index import SearchIndex

    qa.jobs.index = SearchIndex(async_session_factory)
    refused = await qa.start("kart limiti")
    assert (refused.status_code, refused.json()["detail"]["code"]) == (
        503,
        "search_index_not_ready",
    )


# --- Requirement 5: the analysis could not run -------------------------------------------------


async def test_without_a_chat_model_the_answer_says_why(dd: DataDictionary) -> None:
    async for qa in qa_harness(dd, connect=False):
        analysis_id = await qa.started("kart limiti")
        done = await qa.finished(analysis_id)
        assert (done["state"], done["flow"]) == ("completed", "unavailable")
        reason = "Sohbet modeli bağlı değil; Yönetim → Yapay zekâ sayfasından bir model bağlayın."
        assert done["result"]["summary"] == f"Analiz yapılamadı: {reason}"
        assert done["result"]["objects"] == [] and done["result"]["verdict"] == "BULUNAMADI"
        row = await record(analysis_id)
        assert (row["unavailable_reason"], row["model"]) == (reason, "")
        assert await saved_answer_count() == 0
        report = await qa.request("GET", f"/analyses/{analysis_id}/report")
        assert report.status_code == 200


async def test_a_server_that_does_not_answer_is_named_without_its_address(qa: Qa) -> None:
    qa.model.down = True
    analysis_id = await qa.started("kart limiti")
    done = await qa.finished(analysis_id)
    reason = "Model sunucusu yanıt vermedi: Sunucu HTTP 500 döndürdü"
    assert done["result"]["fallback"] == reason
    assert "127.0.0.1" not in json.dumps(done)
    row = await record(analysis_id)
    check = next(s for s in row["steps"] if s["key"] == "model_check")
    assert check["status"] == "error" and check["check"]["http_status"] == 500
    assert "127.0.0.1" not in json.dumps(row["steps"])
    status = (await qa.request("GET", "/status")).json()
    assert status["llm_state"]["state"] == "down" and "127.0.0.1" not in json.dumps(status)


# --- Requirement 15 and 17 -----------------------------------------------------------------------


async def test_the_status_reports_the_serving_dictionary_and_the_model(qa: Qa) -> None:
    response = await qa.request("GET", "/status")
    assert response.status_code == 200, response.text
    body = response.json()
    engine = qa.dd.index.engine()
    assert body["columns"] == len(engine.dictionary.columns) and body["objects"] > 0
    assert body["dictionary_version"] == engine.dictionary.version
    assert body["llm"] == "fake-analyst" and body["shortlist"] == 14
    assert body["llm_state"] == {"state": "ok", "model": "fake-analyst", "code": None, "reason": ""}
    assert (await qa.without_device("GET", "/status")).status_code == 400


async def test_saved_answers_are_summarized_and_cleared_by_a_manager(qa: Qa) -> None:
    analysis_id = await qa.started("kart limiti")
    await qa.finished(analysis_id)
    # A visitor has no session: the manager's endpoints answer 401; an ordinary account 403.
    assert (await qa.request("GET", "/saved-answers/summary")).status_code == 401
    assert (await qa.request("DELETE", "/saved-answers")).status_code == 401
    assert (await qa.admin_request("GET", "/saved-answers/summary", qa.user)).status_code == 403
    assert (await qa.admin_request("DELETE", "/saved-answers", qa.user)).status_code == 403
    summary = (await qa.admin_request("GET", "/saved-answers/summary", qa.dd.manager)).json()
    assert (summary["total"], summary["usable"]) == (1, 1) and summary["newest_at"]
    top3 = await qa.started("kart limiti", top=3, fresh=True)
    await qa.finished(top3)
    summary = (await qa.admin_request("GET", "/saved-answers/summary", qa.dd.manager)).json()
    assert (summary["total"], summary["usable"]) == (2, 1)
    cleared = await qa.admin_request("DELETE", "/saved-answers", qa.dd.manager)
    assert cleared.json() == {"removed": 2}
    again = await qa.admin_request("DELETE", "/saved-answers", qa.dd.manager)
    assert again.json() == {"removed": 0}
    fresh = await qa.start("kart limiti")
    assert fresh.json()["state"] == "queued"
    await qa.finished(fresh.json()["analysis_id"])


# --- Requirement 3, 9 and 14: pinned engines, concurrency and one analysis per question ------


async def test_a_running_job_keeps_its_engine_and_writes_no_stale_answer(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    analysis_id = await qa.started(QUESTION)
    async with asyncio.timeout(5):
        await qa.model.chat_started.wait()
    before = qa.dd.index.engine()
    changed = await qa.dd.patch_settings({"analyst.shortlist": 6})
    assert changed.status_code == 200, changed.text
    assert qa.dd.index.engine() is not before
    qa.model.hold.set()
    done = await qa.finished(analysis_id)
    assert done["flow"] == "analyst"
    first_system = qa.model.chat_requests()[0].json()["messages"][0]["content"]
    assert "14" in first_system
    assert await saved_answer_count() == 0
    again = await qa.start(QUESTION)
    assert again.json()["state"] == "queued"
    await qa.finished(again.json()["analysis_id"])
    later_system = qa.model.chat_requests()[2].json()["messages"][0]["content"]
    assert later_system != first_system


async def _model_calls(qa: Qa, count: int) -> None:
    async with asyncio.timeout(5):
        while len(qa.model.chat_requests()) < count:
            await asyncio.sleep(0.02)
    await asyncio.sleep(0.2)


async def test_concurrency_two_never_runs_three(dd: DataDictionary) -> None:
    async for qa in qa_harness(dd, concurrency=2):
        third_owner = await qa.dd.auth.account(qa.dd.admin, "kullanici")
        qa.model.hold = asyncio.Event()
        owners = (qa.user, qa.other, third_owner)
        questions = ("kart limiti", "mevduat bakiyesi", "kredi riski")
        ids = [await qa.started(q, who) for q, who in zip(questions, owners, strict=True)]
        await _model_calls(qa, 2)
        assert len(qa.model.chat_requests()) == 2
        third = await qa.job(ids[2], third_owner)
        assert (third["state"], third["ahead"]) == ("queued", 2)
        qa.model.hold.set()
        for analysis_id, who in zip(ids, owners, strict=True):
            assert (await qa.finished(analysis_id, who))["flow"] == "analyst"
        assert qa.model.fake.peak <= 2


async def test_two_owners_run_in_parallel_and_one_owner_waits_for_itself(
    dd: DataDictionary,
) -> None:
    # Requirement 9 b, c, Decision 27: different owners do not wait for each other; an owner's
    # second job waits for its first and does not hold up another owner's job behind it.
    async for qa in qa_harness(dd, concurrency=4):
        qa.model.hold = asyncio.Event()
        first = await qa.started("kart limiti", qa.user)
        second_of_user = await qa.started("mevduat bakiyesi", qa.user)
        of_other = await qa.started("kredi riski", qa.other)
        await _model_calls(qa, 2)
        assert len(qa.model.chat_requests()) == 2
        assert (await qa.job(first))["state"] == "running"
        assert (await qa.job(of_other, qa.other))["state"] == "running"
        assert (await qa.job(second_of_user))["state"] == "queued"
        qa.model.hold.set()
        done_first = await qa.finished(first)
        done_second = await qa.finished(second_of_user)
        assert done_first["flow"] == done_second["flow"] == "analyst"
        assert (await qa.finished(of_other, qa.other))["flow"] == "analyst"
        assert done_second["started_at"] >= done_first["finished_at"]
        assert qa.model.fake.peak == 2


async def test_the_same_question_asked_at_once_is_analysed_once(dd: DataDictionary) -> None:
    async for qa in qa_harness(dd, concurrency=2):
        qa.model.hold = asyncio.Event()
        first = await qa.started(QUESTION)
        async with asyncio.timeout(5):
            await qa.model.chat_started.wait()
        second = await qa.started(QUESTION, qa.other)
        await asyncio.sleep(0.3)
        assert (await qa.job(second, qa.other))["state"] == "queued"
        qa.model.hold.set()
        assert (await qa.finished(first))["flow"] == "analyst"
        assert (await qa.finished(second, qa.other))["flow"] == "reused"
        assert len(qa.model.chat_requests()) == 2  # one analysis: two model calls


async def test_a_saved_answer_store_failure_does_not_stop_the_analysis(qa: Qa) -> None:
    def broken() -> Any:
        raise ConnectionError("veritabanı yok")

    qa.jobs.saved_answers._session_factory = broken  # type: ignore[assignment]
    analysis_id = await qa.started(QUESTION)
    done = await qa.finished(analysis_id)
    assert done["flow"] == "analyst"
    assert await saved_answer_count() == 0
