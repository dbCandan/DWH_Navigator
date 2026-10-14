"""The administration screen's analysis record endpoints against PostgreSQL.

data-dictionary/PRDs/008-analysis-records Requirement 1-3, 5-12 (Acceptance 1 and 2): only finished
records, Istanbul periods, Turkish-folded text search with escaped wildcards, the "until" bound,
paging, the summary as the source computed it, daily counts with empty days, askers, the detail,
deletion by filter or all with its log event and metric, the saved answer link, roles.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.session import async_session_factory
from app.domain.turkish_text import fold
from app.services.analysis.pipeline import ISTANBUL
from tests.fakes.telemetry import TelemetryCapture
from tests.integration.conftest import (
    CLIENT_ADDRESS,
    VISITOR_HOST,
    RecordingHandler,
    SignedIn,
    visitor_headers,
    visitor_public_id,
    visitor_row_id,
)
from tests.integration.data_dictionary import DataDictionary, sql

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


async def user_id(who: SignedIn) -> int:
    ((value,),) = await sql("SELECT user_id FROM app_user WHERE public_id = :p", p=who.public_id)
    return int(value)


async def tenant_id() -> int:
    ((value,),) = await sql("SELECT tenant_id FROM tenant WHERE code = 'platform'")
    return int(value)


async def add(
    who: SignedIn,
    *,
    query: str = "kart limiti",
    state: str = "completed",
    flow: str | None = "analyst",
    asked_at: datetime | None = None,
    verdict: str | None = "VAR",
    duration_ms: int = 1000,
    model: str = "fake-analyst",
    summary: str = "VAR. Özet",
    table_keys: list[str] | None = None,
    list_file_name: str | None = None,
    phases: dict[str, int] | None = None,
    llm: tuple[int, int, int] = (2, 100, 50),
) -> str:
    public_id = str(uuid4())
    keys = table_keys if table_keys is not None else ["DB.dbo.vKart"]
    search = fold(" ".join([query, model, summary, list_file_name or "", *keys]))
    columns: dict[str, Any] = {
        "public_id": public_id,
        "tenant_id": await tenant_id(),
        "asked_by": await user_id(who),
        "state": state,
        "flow": flow,
        "asked_at": asked_at or NOW - timedelta(minutes=5),
        "query": query,
        "fresh": False,
        "origin": "list" if list_file_name else "question",
        "list_file_name": list_file_name,
        "list_position": 3 if list_file_name else None,
        "model": model,
        "verdict": verdict,
        "summary": summary,
        "table_keys": keys,
        "duration_ms": duration_ms,
        "llm_calls": llm[0],
        "prompt_tokens": llm[1],
        "completion_tokens": llm[2],
        "search_key": search,
        "steps": [],
        **{f"phase_{k}_ms": v for k, v in (phases or {}).items()},
    }
    names = ", ".join(columns)
    values = ", ".join(
        f"CAST(:{k} AS jsonb)" if k in ("table_keys", "steps") else f":{k}" for k in columns
    )
    import json

    params = {k: json.dumps(v) if k in ("table_keys", "steps") else v for k, v in columns.items()}
    async with async_session_factory() as session:
        await session.execute(
            text(f"INSERT INTO analysis_record ({names}) VALUES ({values})"), params
        )
        await session.commit()
    return public_id


@pytest.fixture
async def ar(dd: DataDictionary) -> AsyncIterator[DataDictionary]:
    await sql("DELETE FROM saved_answer")
    await sql("DELETE FROM analysis_record")
    yield dd


async def test_only_managers_reach_the_endpoints(ar: DataDictionary) -> None:
    user = await ar.auth.account(ar.admin, "kullanici")
    until = quote(NOW.isoformat())
    for method, path in (
        ("GET", "/analysis-records"),
        ("GET", "/analysis-records/summary"),
        ("GET", "/analysis-records/daily-counts"),
        ("GET", "/analysis-records/askers"),
        ("GET", f"/analysis-records/{uuid4()}"),
        ("DELETE", f"/analysis-records?all=true&until={until}"),
    ):
        assert (await ar.request(method, path, user)).status_code == 403, path
        anonymous = await ar.auth.client.request(
            method,
            ar.url(path),
            headers={ar.auth.settings.tenant_header: ar.manager.tenant_id},
        )
        assert anonymous.status_code == 401, path


async def test_running_records_stay_out_of_every_endpoint(ar: DataDictionary) -> None:
    done = await add(ar.manager)
    running = await add(ar.manager, state="running", flow=None, verdict=None)
    queued = await add(ar.manager, state="queued", flow=None, verdict=None)
    page = (await ar.get("/analysis-records")).json()
    assert [i["public_id"] for i in page["items"]] == [done]
    assert (await ar.get("/analysis-records/summary")).json()["count"] == 1
    for hidden in (running, queued):
        response = await ar.get(f"/analysis-records/{hidden}")
        assert response.json()["detail"]["code"] == "analysis_record_not_found"
    deleted = await ar.request(
        "DELETE", f"/analysis-records?all=true&until={quote(NOW.isoformat())}"
    )
    assert deleted.json() == {"deleted_count": 1, "remaining_count": 0}
    left = await sql("SELECT public_id FROM analysis_record ORDER BY public_id")
    assert {r[0] for r in left} == {running, queued}


async def test_periods_text_and_wildcards(ar: DataDictionary) -> None:
    other = await ar.auth.account(ar.admin, "kullanici")
    today_start = datetime.combine(NOW.astimezone(ISTANBUL).date(), datetime.min.time(), ISTANBUL)
    just_today = await add(
        ar.manager, query="İŞLEM hacmi", asked_at=today_start + timedelta(seconds=1)
    )
    yesterday = await add(
        ar.manager, query="islem sayısı", asked_at=today_start - timedelta(seconds=1)
    )
    old = await add(other, query="İşlem 100%_oran", asked_at=NOW - timedelta(days=10))
    ancient = await add(other, query="kredi", asked_at=NOW - timedelta(days=400), flow="cancelled",
                        verdict=None)  # fmt: skip

    async def ids(query: str) -> list[str]:
        response = await ar.get(f"/analysis-records?{query}")
        assert response.status_code == 200, response.text
        return [i["public_id"] for i in response.json()["items"]]

    assert set(await ids("period=today")) == {just_today}
    week = await ids("")
    assert week[:2] == [just_today, yesterday] or set(week) == {just_today, yesterday}
    assert set(await ids("period=30d")) == {just_today, yesterday, old}
    assert set(await ids("period=all")) == {just_today, yesterday, old, ancient}
    for needle in ("İŞLEM", "işlem", "islem"):
        assert set(await ids(f"period=all&q={needle}")) == {just_today, yesterday, old}
    assert await ids("period=all&q=%25_") == [old]
    assert await ids("period=all&q=0%25") == [old]
    assert await ids("period=all&q=_x") == []
    assert await ids(f"period=all&asked_by={other.public_id}") == [old, ancient]
    assert await ids("period=all&flow=cancelled") == [ancient]
    until = (NOW - timedelta(days=5)).isoformat()

    assert await ids(f"period=all&until={quote(until)}") == [old, ancient]
    for bad in ("period=year", "flow=önbellek", "asked_by=kisi", f"q={'a' * 201}",
                "until=dun", "until=2026-10-08T10:00:00", "page=0", "page_size=501"):  # fmt: skip
        response = await ar.get(f"/analysis-records?{bad}")
        assert (response.status_code, response.json()["detail"]["code"]) == (
            422, "invalid_filter"
        ), bad  # fmt: skip


async def test_pages_follow_the_snapshot(ar: DataDictionary) -> None:
    now = datetime.now(UTC)  # not the module's NOW: a long run makes that one the past
    created = [await add(ar.manager, asked_at=now - timedelta(minutes=10)) for _ in range(3)]
    first = (await ar.get("/analysis-records?page_size=2")).json()
    assert first["total"] == 3 and len(first["items"]) == 2
    snapshot = first["snapshot_at"]
    newer = await add(ar.manager, asked_at=datetime.now(UTC) + timedelta(seconds=30))

    second = (await ar.get(f"/analysis-records?page_size=2&page=2&until={quote(snapshot)}")).json()
    shown = [i["public_id"] for i in first["items"] + second["items"]]
    assert sorted(shown) == sorted(created) and newer not in shown
    # Equal times: the record opened last comes first.
    assert shown == list(reversed(created))


async def test_the_summary_is_the_sources_computation(ar: DataDictionary) -> None:
    other = await ar.auth.account(ar.admin, "kullanici")
    await sql("UPDATE app_user SET display_name = 'Zeynep' WHERE public_id = :p", p=other.public_id)
    await sql(
        "UPDATE app_user SET display_name = 'Ahmet' WHERE public_id = :p", p=ar.manager.public_id
    )
    durations = [1000, 2000, 3000, 10000]
    for ms in durations:
        await add(ar.manager, duration_ms=ms, phases={"rule_hints": 200, "queue": 0})
    await add(other, flow="reused", verdict="KISMEN VAR", duration_ms=50,
              phases={"saved_answer_lookup": 40})  # fmt: skip
    await add(other, flow="unavailable", verdict="BULUNAMADI", duration_ms=500)
    await add(other, flow="failed", verdict=None, duration_ms=700, llm=(0, 0, 0))
    body = (await ar.get("/analysis-records/summary")).json()
    assert body["count"] == 7 and body["with_result"] == 6 and body["with_tables"] == 5
    assert body["flows"] == {
        "analyst": 4, "reused": 1, "unavailable": 1, "cancelled": 0, "failed": 1,
        "interrupted": 0,
    }  # fmt: skip
    # The source's quantile on [1000, 2000, 3000, 10000], with its floating-point result.
    assert (body["analyst_p50_ms"], body["analyst_p90_ms"]) == (2500, 3000 + 7000 * (3 * 0.9 - 2))
    every = sorted([*durations, 50, 500, 700])
    assert body["p50_ms"] == every[3] and body["max_ms"] == 10000
    phases = {p["phase"]: p for p in body["phases"]}
    assert phases["rule_hints"] == {"phase": "rule_hints", "average_ms": 200, "count": 4}
    assert phases["queue"]["count"] == 0 and phases["queue"]["average_ms"] is None
    assert phases["saved_answer_lookup"]["count"] == 1
    assert (body["llm_calls"], body["prompt_tokens"], body["completion_tokens"]) == (
        12, 600, 300
    )  # fmt: skip
    assert [(a["display_name"], a["count"]) for a in body["askers"]] == [
        ("Ahmet", 4), ("Zeynep", 3)
    ]  # fmt: skip
    empty = (await ar.get("/analysis-records/summary?flow=interrupted")).json()
    assert empty["count"] == 0 and empty["p50_ms"] is None and empty["analyst_p50_ms"] is None
    askers = (await ar.get("/analysis-records/askers")).json()["items"]
    assert [a["display_name"] for a in askers] == ["Ahmet", "Zeynep"]


async def test_a_visitor_is_shown_by_its_host_and_address(ar: DataDictionary) -> None:
    # 008 Decision 2, Requirement 9; application-foundation 003-anonymous-visitor Requirement 7.
    person = await ar.auth.account(ar.admin, "kullanici")
    seen = await ar.auth.client.get(f"{ar.auth.prefix}/status", headers=visitor_headers(person))
    assert seen.status_code == 200, seen.text
    visitor = await visitor_row_id(person)
    with_host = await add(ar.manager, query="ziyaretçi sorusu")
    without_host = await add(ar.manager, query="adressiz soru")
    for record_id, host in ((with_host, "pc-17.kurum"), (without_host, None)):
        await sql(
            "UPDATE analysis_record SET asked_by = NULL, asked_by_visitor_id = :v, "
            "client_address = '10.0.0.17', client_host = :h WHERE public_id = :p",
            v=visitor,
            h=host,
            p=record_id,
        )
    items = {
        i["public_id"]: i["asked_by"] for i in (await ar.get("/analysis-records")).json()["items"]
    }
    public_id = await visitor_public_id(person)
    assert items[with_host] == {
        "public_id": public_id, "display_name": "pc-17.kurum · 10.0.0.17", "kind": "visitor"
    }  # fmt: skip
    assert items[without_host]["display_name"] == "10.0.0.17"
    only = (await ar.get(f"/analysis-records?asked_by={public_id}")).json()["items"]
    assert {i["public_id"] for i in only} == {with_host, without_host}
    askers = (await ar.get("/analysis-records/askers")).json()["items"]
    assert {
        "public_id": public_id, "display_name": f"{VISITOR_HOST} · {CLIENT_ADDRESS}", "kind": "visitor"
    } in askers  # fmt: skip
    summary = (await ar.get("/analysis-records/summary")).json()
    assert {a["kind"] for a in summary["askers"]} == {"visitor"}
    detail = (await ar.get(f"/analysis-records/{with_host}")).json()
    assert detail["asked_by"]["kind"] == "visitor"


async def test_daily_counts_are_istanbul_days_with_zeros(ar: DataDictionary) -> None:
    today = NOW.astimezone(ISTANBUL).date()
    midnight = datetime.combine(today, datetime.min.time(), ISTANBUL)
    await add(ar.manager, asked_at=midnight + timedelta(minutes=1))
    await add(ar.manager, asked_at=midnight - timedelta(minutes=1), verdict="BULUNAMADI")
    await add(ar.manager, asked_at=midnight - timedelta(days=2), verdict=None, flow="failed")
    days = (await ar.get("/analysis-records/daily-counts?days=3")).json()["days"]
    assert [d["date"] for d in days] == [(today - timedelta(days=n)).isoformat() for n in (2, 1, 0)]
    assert [(d["with_tables"], d["without_tables"]) for d in days] == [(0, 1), (0, 1), (1, 0)]
    assert len((await ar.get("/analysis-records/daily-counts")).json()["days"]) == 14
    assert (await ar.get("/analysis-records/daily-counts?days=32")).status_code == 422


async def test_the_detail_has_the_steps_but_not_the_answer(ar: DataDictionary) -> None:
    public_id = await add(ar.manager, list_file_name="liste.xlsx", phases={"analyst_pick": 900})
    await sql(
        "UPDATE analysis_record SET result = CAST(:r AS jsonb), steps = CAST(:s AS jsonb), "
        "steps_truncated = true WHERE public_id = :p",
        r='{"summary": "tam cevap"}',
        s='[{"seq": 0, "parent": null, "name": "Model sunucusu kontrolü", "kind": "step", '
        '"key": "model_check", "start_ms": 0, "ms": 5, "status": "ok", "detail": "m", '
        '"check": {"outcome": "ok", "http_status": 200, "duration_ms": 5, "cached": false}}]',
        p=public_id,
    )
    body = (await ar.get(f"/analysis-records/{public_id}")).json()
    assert "result" not in body and "tam cevap" not in str(body)
    assert body["phases"]["analyst_pick"] == 900 and body["steps_truncated"] is True
    assert body["steps"][0]["key"] == "model_check" and body["steps"][0]["check"]["cached"] is False
    assert (body["origin"], body["list_file_name"], body["list_position"]) == (
        "list", "liste.xlsx", 3
    )  # fmt: skip
    listed = (await ar.get("/analysis-records")).json()["items"][0]
    assert "summary" not in listed and "steps" not in listed


async def test_deletion_needs_a_scope_and_keeps_later_records(
    ar: DataDictionary,
    recorded_logs: RecordingHandler,
    telemetry_capture: TelemetryCapture,
) -> None:
    import logging

    logging.getLogger("app.analysis").setLevel(logging.INFO)
    stopped = await add(ar.manager, flow="cancelled", verdict=None)
    kept = await add(ar.manager)
    await sql(
        "INSERT INTO saved_answer (public_id, tenant_id, query_text, text_key, meaning_key, "
        "fingerprint, result, answered_at, analysis_public_id) VALUES (gen_random_uuid()::text, "
        ":t, 'kart', 'kart', '', '0123456789abcdef', '{}'::jsonb, now(), :p)",
        t=await tenant_id(),
        p=stopped,
    )
    until = NOW.isoformat()

    for scope in ("", f"?until={quote(until)}", "?all=true"):
        response = await ar.request("DELETE", f"/analysis-records{scope}")
        assert response.json()["detail"]["code"] == "analysis_delete_scope_missing", scope
    later = await add(
        ar.manager, flow="cancelled", verdict=None, asked_at=NOW + timedelta(minutes=1)
    )
    path = f"/analysis-records?flow=cancelled&period=all&until={quote(until)}"
    first = await ar.request("DELETE", path)
    assert first.json() == {"deleted_count": 1, "remaining_count": 2}
    again = await ar.request("DELETE", path)
    assert again.json() == {"deleted_count": 0, "remaining_count": 2}
    rows = await sql("SELECT public_id FROM analysis_record")
    assert {r[0] for r in rows} == {kept, later}
    link = await sql("SELECT analysis_public_id FROM saved_answer")
    assert link == [(None,)]
    events = recorded_logs.events("analysis_record.deleted")
    assert events[0] == {
        "event": "analysis_record.deleted",
        "count": 1,
        "scope": "filter",
        "user_public_id": ar.manager.public_id,
    }
    assert telemetry_capture.value("dwhnavigator_analysis_records_deleted_total") == 1
    everything = await ar.request("DELETE", f"/analysis-records?all=true&until={quote(until)}")
    assert everything.json() == {"deleted_count": 1, "remaining_count": 1}


async def test_an_old_finished_record_is_kept(ar: DataDictionary) -> None:
    public_id = await add(ar.manager, asked_at=NOW - timedelta(days=400))
    assert [
        i["public_id"] for i in (await ar.get("/analysis-records?period=all")).json()["items"]
    ] == [public_id]
