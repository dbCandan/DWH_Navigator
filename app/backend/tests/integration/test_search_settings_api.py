"""Search settings and the search index on PostgreSQL (search-settings Acceptance 1 and 2).

Requirement 2-6 (read, check, store only changes, build then write), 10 (readiness waits for the
first engine; a stored value off the schema stops the start), 11 (one change at a time, 503 after
the wait), 12 (no analysis lock), 14-15 (rebuild, state, stale) and 26 (roles).
"""

import asyncio
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.main import app
from app.services.search_index import IndexState, SearchIndex
from tests.integration.conftest import RecordingHandler
from tests.integration.data_dictionary import (
    DataDictionary,
    database_ready,
    error,
    sql,
    started_index,
)

pytestmark = pytest.mark.integration


async def stored() -> list[tuple[str, Any, bool]]:
    rows = await sql(
        "SELECT setting_key, value, is_deleted FROM search_setting ORDER BY search_setting_id"
    )
    return [(str(k), v, bool(d)) for k, v, d in rows]


async def test_every_endpoint_needs_a_session_and_the_manager_role(dd: DataDictionary) -> None:
    user = await dd.auth.account(dd.admin, "kullanici")
    calls = [
        ("GET", "/search-settings", {}),
        ("PATCH", "/search-settings", {"json": {"values": {}}}),
        ("GET", "/search-index", {}),
        ("POST", "/search-index/rebuilds", {}),
    ]
    for method, path, kwargs in calls:
        anonymous = await dd.auth.client.request(
            method,
            dd.url(path),
            headers={dd.auth.settings.tenant_header: dd.manager.tenant_id},
            **kwargs,
        )
        assert error(anonymous) == (401, "not_authenticated"), path
        assert error(await dd.request(method, path, user, **kwargs)) == (403, "forbidden"), path


async def test_the_schema_values_and_defaults(dd: DataDictionary) -> None:
    body = (await dd.get("/search-settings")).json()
    assert [s["id"] for s in body["sections"]] == ["analyst", "terms", "ranking", "words", "cache"]
    assert sum(len(s["fields"]) for s in body["sections"]) == 25
    assert body["values"] == body["defaults"] and body["values"]["analyst.shortlist"] == 14
    assert body["values"]["analyst.shortlist_max_tokens"] == 8000
    assert body["sections"][3]["fields"][5]["effect"] == "reindex"


async def test_a_save_stores_only_changed_values_and_applies_them(
    dd: DataDictionary, recorded_logs: RecordingHandler
) -> None:
    first = dd.index.engine()
    response = await dd.patch_settings({"search.bm25.k1": 1.5, "analyst.shortlist": 14})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] == ["search.bm25.k1"] and body["values"]["search.bm25.k1"] == 1.5
    assert body["index"]["trigger"] == "settings" and body["elapsed_ms"] >= 0
    assert await stored() == [("search.bm25.k1", 1.5, False)]
    reindexed = dd.index.engine()
    assert reindexed.bm25 is not first.bm25 and reindexed.bm25.k1 == 1.5

    immediate = await dd.patch_settings({"cache.enabled": False})
    assert immediate.json()["changed"] == ["cache.enabled"]
    assert dd.index.engine().bm25 is reindexed.bm25  # no word-index field changed
    assert dd.index.engine().settings.cache.enabled is False

    back = await dd.patch_settings({"search.bm25.k1": 1.2, "cache.enabled": True})
    assert back.json()["changed"] == ["search.bm25.k1", "cache.enabled"]
    assert await stored() == [
        ("search.bm25.k1", 1.5, True),
        ("cache.enabled", False, True),
    ]
    assert (await dd.get("/search-settings")).json()["values"]["search.bm25.k1"] == 1.2
    events = recorded_logs.events("search_settings.changed")
    assert [(e["keys"], e["effect"]) for e in events] == [
        ("search.bm25.k1", "reindex"),
        ("cache.enabled", "immediate"),
        ("search.bm25.k1,cache.enabled", "reindex"),
    ]
    assert all(e["user_public_id"] == dd.manager.public_id for e in events)


async def test_nothing_changes_without_a_changed_value(dd: DataDictionary) -> None:
    serving = dd.index.serving
    for values in ({}, {"analyst.shortlist": 14}):
        response = await dd.patch_settings(values)
        assert response.status_code == 200 and response.json()["changed"] == []
    assert dd.index.serving is serving and await stored() == []


async def test_a_refused_value_writes_nothing(dd: DataDictionary) -> None:
    serving = dd.index.serving
    unknown = await dd.patch_settings({"llm.endpoint": "http://x", "analyst.shortlist": 5})
    assert error(unknown) == (422, "search_setting_unknown")
    assert unknown.json()["detail"]["message"] == "Bilinmeyen ayar: llm.endpoint"
    invalid = await dd.patch_settings({"analyst.shortlist": "5", "search.bm25.b": 2})
    assert error(invalid) == (422, "search_setting_invalid")
    assert invalid.json()["detail"]["message"] == (
        "Kolonları okunacak aday tablo sayısı: sayı olmalı; BM25 b: 0 ile 1 arasında olmalı"
    )
    assert error(await dd.request("PATCH", "/search-settings", json={"values": 3})) == (
        422,
        "invalid_request",
    )
    assert await stored() == [] and dd.index.serving is serving


async def test_a_failed_build_writes_no_value(dd: DataDictionary) -> None:
    from tests.integration.data_dictionary import first_then

    def broken(*_: Any) -> Any:
        raise RuntimeError("x")

    dd.use_index(await started_index(builder=first_then(broken)))
    response = await dd.patch_settings({"analyst.shortlist": 9})
    assert error(response) == (500, "search_index_build_failed")
    assert await stored() == []
    state = (await dd.get("/search-index")).json()
    assert state["state"] == "ready" and state["last_failure"]["trigger"] == "settings"


async def test_a_change_waiting_longer_than_the_queue_allows_is_503(dd: DataDictionary) -> None:
    dd.use_index(await started_index(queue_timeout=0.2))
    index = dd.index
    await index._lock.acquire()  # another change is being applied
    try:
        response = await dd.patch_settings({"analyst.shortlist": 9})
        rebuild = await dd.request("POST", "/search-index/rebuilds")
    finally:
        index._lock.release()
    assert error(response) == (503, "search_change_busy")
    assert response.json()["detail"]["message"] == (
        "Başka bir değişiklik uygulanıyor; biraz sonra yeniden deneyin."
    )
    assert error(rebuild) == (503, "search_change_busy")
    assert await stored() == []


async def test_a_change_does_not_wait_for_a_running_analysis(dd: DataDictionary) -> None:
    analysis_engine = dd.index.engine()  # an analysis holds its engine for its whole run
    response = await dd.patch_settings({"analyst.shortlist": 9})
    assert response.status_code == 200
    assert analysis_engine.settings.analyst.shortlist == 14
    assert dd.index.engine().settings.analyst.shortlist == 9


async def test_the_index_state_rebuild_and_stale(
    dd: DataDictionary, recorded_logs: RecordingHandler
) -> None:
    state = (await dd.get("/search-index")).json()
    assert state["state"] == "ready" and state["stale_inputs"] == []
    assert (state["columns"], state["objects"], state["dictionary_version"]) == (0, 0, "")
    assert state["running"] is None and state["last_failure"] is None
    rebuilt = await dd.request("POST", "/search-index/rebuilds")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["trigger"] == "manual" and rebuilt.json()["elapsed_ms"] >= 0

    # Another process changes the database: the state shows it, once logged.
    await sql(
        "INSERT INTO search_setting (tenant_id, setting_key, value) SELECT tenant_id, "
        "'analyst.shortlist', '9' FROM tenant WHERE code = 'platform'"
    )
    for _ in range(2):
        stale = (await dd.get("/search-index")).json()
        assert stale["state"] == "stale" and stale["stale_inputs"] == ["settings"]
    assert recorded_logs.events("search_index.stale_detected") == [
        {"event": "search_index.stale_detected", "inputs": "settings"}
    ]
    await dd.request("POST", "/search-index/rebuilds")
    assert (await dd.get("/search-index")).json()["state"] == "ready"
    assert dd.index.engine().settings.analyst.shortlist == 9


async def test_readiness_waits_for_the_first_engine(dd: DataDictionary) -> None:
    index = SearchIndex(async_session_factory)
    dd.use_index(index)
    readiness = f"{get_settings().api_prefix}/readiness"
    liveness = f"{get_settings().api_prefix}/liveness"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.get(readiness)).status_code == 503
        assert (await client.get(liveness)).status_code == 200
        assert (await dd.get("/search-index")).json()["state"] == "building"
        await index.run_startup(database_ready)
        assert (await client.get(readiness)).status_code == 200
        # A later rebuild keeps the process ready.
        assert (await dd.request("POST", "/search-index/rebuilds")).status_code == 200
        assert (await client.get(readiness)).status_code == 200


async def test_a_stored_value_off_the_schema_stops_the_start(
    dd: DataDictionary, recorded_logs: RecordingHandler
) -> None:
    await sql(
        "INSERT INTO search_setting (tenant_id, setting_key, value) SELECT tenant_id, "
        "'analyst.removed', '1' FROM tenant WHERE code = 'platform'"
    )
    stopped: list[str] = []
    index = SearchIndex(async_session_factory)
    await index.run_startup(database_ready, lambda: stopped.append("exit"))
    assert stopped == ["exit"] and not index.is_serving
    assert recorded_logs.events("search_settings.startup_invalid") == [
        {
            "event": "search_settings.startup_invalid",
            "key": "analyst.removed",
            "reason": "unknown",
        }
    ]
    status = await index.status()
    assert status.state is IndexState.BUILDING


async def test_changes_from_two_requests_run_one_after_the_other(dd: DataDictionary) -> None:
    first, second = await asyncio.gather(
        dd.patch_settings({"analyst.shortlist": 9}),
        dd.patch_settings({"analyst.shortlist": 10}),
    )
    assert first.status_code == second.status_code == 200
    assert sorted(
        [first.json()["values"]["analyst.shortlist"], second.json()["values"]["analyst.shortlist"]]
    ) == [9, 10]
    final = (await dd.get("/search-settings")).json()["values"]["analyst.shortlist"]
    assert dd.index.engine().settings.analyst.shortlist == final
    assert [row for row in await stored() if not row[2]] == [("analyst.shortlist", final, False)]
