"""Dictionary explorer endpoints over HTTP and PostgreSQL (data-dictionary 007-dictionary-explorer
Requirement 3, 10, 11, 19, Decision 2; Acceptance 1).

The synthetic dictionary is imported through the API; the answers are the in-process explorer
functions' on the serving engine (whose parity with the source is ``test_explorer_parity``), the
roles and errors are the PRD's, a running analysis never makes a search wait and the content layer
never blocks the event loop.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote
from uuid import UUID

import pytest

from app.core.security import create_access_token
from app.db.session import async_session_factory
from app.services import explorer
from app.services.search_index import SearchIndex
from tests.integration.analysis import Qa, qa_harness
from tests.integration.conftest import SignedIn
from tests.integration.data_dictionary import SYNTHETIC_WORKBOOK, DataDictionary, error

pytestmark = pytest.mark.integration

QUESTION = "kredi kartı limit doluluk oranı"


@pytest.fixture
async def user(dd: DataDictionary) -> SignedIn:
    imported = await dd.import_dictionary(SYNTHETIC_WORKBOOK.read_bytes())
    assert imported.status_code in (200, 201), imported.text
    return await dd.auth.account(dd.admin, "kullanici")


def roleless(who: SignedIn) -> dict[str, str]:
    token = create_access_token(
        subject=UUID(who.public_id),
        username=who.username,
        tenant_id=UUID(who.tenant_id),
        roles=[],
        permissions=[],
        is_super_admin=False,
    )
    return {"Authorization": f"Bearer {token}"}


async def search(dd: DataDictionary, who: SignedIn, query: Any) -> Any:
    return await dd.request("POST", "/explorer/table-searches", who, json={"query": query})


async def test_the_star_map_is_every_served_table(dd: DataDictionary, user: SignedIn) -> None:
    response = await dd.get("/explorer/galaxy", user)
    assert response.status_code == 200, response.text
    body = response.json()
    rows = explorer.table_index(dd.index.engine())
    assert body == {"items": explorer.galaxy(rows), "total": len(rows)}
    assert body["total"] == len(dd.index.engine().objects) >= 60
    names = [star["name"] for star in body["items"]]
    assert names == sorted(names)
    assert "Diğer" in {star["group"] for star in body["items"]}  # tables without a profile
    assert set(body["items"][0]) == {"key", "name", "schema", "group", "columns"}


async def test_the_table_search_answers_as_the_source_rules(
    dd: DataDictionary, user: SignedIn
) -> None:
    engine = dd.index.engine()
    rows = explorer.table_index(engine)
    for query in ("", "ab", "kart", QUESTION, "  PartyId  "):
        response = await search(dd, user, query)
        assert response.status_code == 200, response.text
        body = response.json()
        expected = explorer.search(engine, rows, query)
        assert body["elapsed_ms"] >= 0
        assert {**body, "elapsed_ms": 0} == {**expected, "elapsed_ms": 0}, query
    browse = (await search(dd, user, "")).json()
    assert browse["query"] == "" and len(browse["items"]) == min(60, len(rows))
    assert {item["match"] for item in browse["items"]} == {""}
    short = (await search(dd, user, "ab")).json()
    assert "içerik" not in short["counts"] and short["concepts"] == []
    full = (await search(dd, user, QUESTION)).json()
    assert full["counts"].get("içerik", 0) > 0 and full["concepts"]
    content = next(i for i in full["items"] if i["match"] == "içerik")
    assert {"score", "level", "matched", "covered", "missing", "signal"} <= set(content)
    named = next(i for i in short["items"] if i["match"] == "ad")
    assert "score" not in named


async def test_the_search_text_is_bounded_and_the_body_checked(
    dd: DataDictionary, user: SignedIn
) -> None:
    assert (await search(dd, user, "  " + "x" * 4000 + "  ")).status_code == 200
    assert error(await search(dd, user, "x" * 4001)) == (422, "query_too_long")
    assert error(await search(dd, user, 5)) == (422, "invalid_request")
    extra = await dd.request(
        "POST", "/explorer/table-searches", user, json={"query": "a", "q": "b"}
    )
    assert error(extra) == (422, "invalid_request")


async def test_a_table_detail_and_its_join_keys(dd: DataDictionary, user: SignedIn) -> None:
    engine = dd.index.engine()
    for key in engine.objects:
        response = await dd.get(f"/explorer/tables/{quote(key, safe='')}", user)
        assert response.status_code == 200, response.text
        assert response.json() == explorer.table_detail(engine, key)
    with_keys = [k for k in engine.objects if engine.join_keys.get(k)]
    assert with_keys
    detail = (await dd.get(f"/explorer/tables/{with_keys[0]}", user)).json()
    assert detail["join_keys"] == engine.join_keys[with_keys[0]]
    assert set(detail["columns"][0]) == {
        "key", "column", "object", "description", "synonyms", "pii", "group"
    }  # fmt: skip
    assert error(await dd.get("/explorer/tables/SYNDM.yok.Tablo", user)) == (
        404,
        "table_not_found",
    )
    assert error(await dd.get(f"/explorer/tables/{quote('a/b.c', safe='')}", user)) == (
        404,
        "table_not_found",
    )


async def test_roles(dd: DataDictionary, user: SignedIn) -> None:
    paths = [("GET", "/explorer/galaxy"), ("GET", "/explorer/tables/x.y.z")]
    for method, path in paths:
        anonymous = await dd.request(method, path, user, headers={"Authorization": ""})
        assert anonymous.status_code == 401
        no_role = await dd.request(method, path, user, headers=roleless(user))
        assert no_role.status_code == 403
    for who in (user, dd.manager, dd.admin):
        assert (await dd.get("/explorer/galaxy", who)).status_code == 200
        assert (await search(dd, who, "kart")).status_code == 200
    anonymous = await dd.request(
        "POST", "/explorer/table-searches", user, json={"query": "a"}, headers={"Authorization": ""}
    )
    assert anonymous.status_code == 401
    no_role = await dd.request(
        "POST", "/explorer/table-searches", user, json={"query": "a"}, headers=roleless(user)
    )
    assert no_role.status_code == 403


async def test_before_the_first_index_every_endpoint_is_not_ready(
    dd: DataDictionary, user: SignedIn
) -> None:
    serving = dd.index
    dd.use_index(SearchIndex(async_session_factory))
    try:
        for response in (
            await dd.get("/explorer/galaxy", user),
            await search(dd, user, "kart"),
            await dd.get("/explorer/tables/x.y.z", user),
        ):
            assert error(response) == (503, "search_index_not_ready")
            assert response.headers["retry-after"] == "5"
    finally:
        dd.use_index(serving)


async def test_the_content_layer_does_not_hold_the_event_loop(
    dd: DataDictionary, user: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = explorer.search

    def slow(*args: Any) -> Any:
        time.sleep(1.0)
        return real(*args)

    monkeypatch.setattr(explorer, "search", slow)
    started = time.monotonic()
    searching = asyncio.create_task(search(dd, user, QUESTION))
    await asyncio.sleep(0.1)
    galaxy = await dd.get("/explorer/galaxy", user)
    assert galaxy.status_code == 200
    assert time.monotonic() - started < 0.8  # answered while the search still ran
    assert (await searching).status_code == 200


@pytest.fixture
async def qa(dd: DataDictionary) -> AsyncIterator[Qa]:
    async for each in qa_harness(dd):
        yield each


async def test_a_running_analysis_never_makes_a_search_wait(qa: Qa) -> None:
    qa.model.hold = asyncio.Event()
    analysis_id = await qa.started(QUESTION)
    async with asyncio.timeout(10):
        await qa.model.chat_started.wait()
    started = time.monotonic()
    response = await qa.request("POST", "/explorer/table-searches", json={"query": QUESTION})
    assert response.status_code == 200
    assert (await qa.request("GET", "/explorer/galaxy")).status_code == 200
    assert time.monotonic() - started < 2.0
    assert (await qa.job(analysis_id))["state"] == "running"
    qa.model.hold.set()
