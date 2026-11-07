"""The LLM log: a real adapter against a fake model server, PostgreSQL and the API."""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.db.session import async_session_factory
from app.domain.llm import LlmChatRequest, LlmChatResult, LlmConnection, LlmPurpose
from app.infrastructure.llm.openai_adapter import OpenAICompatibleAdapter
from app.services.llm_call_log import LlmCallLogWriter
from tests.fakes.llm_server import (
    FakeLlmServer,
    RecordedRequest,
    Writer,
    chat_reply,
    json_response,
)
from tests.integration.conftest import AuthHarness, RecordingHandler, SignedIn

pytestmark = pytest.mark.integration

API_KEY = "cagri-kaydi-gizli-anahtar"
MARKER = "kayit-isareti-7f3a"


async def _resolver(host: str, port: int) -> list[str]:
    return ["127.0.0.1"]


async def _sql(statement: str, **params: Any) -> list[Any]:
    async with async_session_factory() as session:
        result = await session.execute(text(statement), params)
        rows = list(result.all()) if result.returns_rows else []
        await session.commit()
    return rows


@dataclass
class Log:
    auth: AuthHarness
    manager: SignedIn
    user: SignedIn
    server: FakeLlmServer
    adapter: OpenAICompatibleAdapter
    tenant_id: int

    @property
    def url(self) -> str:
        return f"{self.auth.prefix}/llm-call-logs"

    async def get(self, path: str = "", who: SignedIn | None = None, **params: Any) -> Any:
        return await self.auth.client.get(
            self.url + path, params=params, headers=self.auth.headers(who or self.manager)
        )

    async def chat(self, user: str = f"Soru {MARKER}") -> LlmChatResult:
        connection = LlmConnection(
            endpoint=self.server.url(),
            chat_model="gemma",
            api_key=API_KEY,
            tenant_id=self.tenant_id,
        )
        result = await self.adapter.chat(
            connection,
            LlmChatRequest(
                system="Sistem talimatı",
                user=user,
                schema={"type": "object"},
                max_tokens=64,
                purpose=LlmPurpose.ANALYSIS,
            ),
        )
        await asyncio.gather(*self.adapter._call_log_writes)
        return result


@pytest.fixture
async def log(auth: AuthHarness) -> AsyncIterator[Log]:
    await _sql("DELETE FROM llm_call_log")
    adapter = OpenAICompatibleAdapter(ca_bundle="", max_concurrent_calls=2, resolver=_resolver)
    adapter.set_call_log(LlmCallLogWriter(async_session_factory, days=7))
    server = await FakeLlmServer().start()

    async def answer(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        writer.write(chat_reply('{"cevap": "Şube ' + MARKER + '"}'))
        await writer.drain()

    server.scenario = answer
    try:
        admin = await auth.super_admin()
        manager = await auth.account(admin, "yonetici")
        user = await auth.account(admin, "kullanici")
        rows = await _sql(
            "SELECT tenant_id FROM tenant WHERE public_id = :id", id=manager.tenant_id
        )
        yield Log(auth, manager, user, server, adapter, rows[0][0])
    finally:
        await server.close()
        await _sql("DELETE FROM llm_call_log")


async def test_the_page_shows_what_went_to_the_model_and_what_came_back(log: Log) -> None:
    assert (await log.chat()).ok

    listing = (await log.get()).json()
    assert (listing["total"], listing["retention_days"]) == (1, log.auth.settings.llm_call_log_days)
    row = listing["rows"][0]
    assert (row["purpose"], row["outcome"], row["model"]) == ("analysis", "ok", "gemma")
    assert (row["prompt_tokens"], row["completion_tokens"]) == (11, 7)
    assert "exchanges" not in row

    detail = (await log.get(f"/{row['public_id']}")).json()
    exchange = detail["exchanges"][0]
    assert f"Soru {MARKER}" in exchange["request"]
    assert "Sistem talimatı" in exchange["request"]
    assert f"Şube {MARKER}" in exchange["response"]
    assert exchange["status"] == 200


async def test_each_refused_request_is_kept_with_its_answer(log: Log) -> None:
    async def refuse_then_answer(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        if len(log.server.requests) == 1:
            writer.write(json_response({"error": "unsupported seed parameter"}, 400))
        else:
            writer.write(chat_reply('{"cevap": "tamam"}'))
        await writer.drain()

    log.server.scenario = refuse_then_answer
    connection = LlmConnection(
        endpoint=log.server.url(), chat_model="gemma", seed=42, tenant_id=log.tenant_id
    )
    await log.adapter.chat(
        connection,
        LlmChatRequest(
            system="s", user="u", schema={}, max_tokens=8, purpose=LlmPurpose.CONNECTION_TEST
        ),
    )
    await asyncio.gather(*log.adapter._call_log_writes)

    row = (await log.get()).json()["rows"][0]
    detail = (await log.get(f"/{row['public_id']}")).json()
    assert [item["status"] for item in detail["exchanges"]] == [400, 200]
    assert "unsupported seed" in detail["exchanges"][0]["response"]
    assert detail["adaptations"] == ["seed"]


async def test_a_call_without_an_answer_keeps_the_request(log: Log) -> None:
    await log.server.close()
    assert not (await log.chat()).ok

    row = (await log.get()).json()["rows"][0]
    detail = (await log.get(f"/{row['public_id']}")).json()
    assert detail["outcome"] != "ok"
    assert detail["exchanges"][0]["status"] is None
    assert MARKER in detail["exchanges"][0]["request"]


async def test_the_key_and_the_address_are_not_stored(log: Log) -> None:
    await log.chat()
    stored = await _sql("SELECT exchanges::text, props::text FROM llm_call_log")
    assert API_KEY not in str(stored)
    assert log.server.url() not in str(stored)


async def test_bodies_stay_out_of_the_application_log(
    log: Log, recorded_logs: RecordingHandler
) -> None:
    logger = logging.getLogger("app.llm")
    level = logger.level
    logger.setLevel(logging.INFO)
    try:
        await log.chat()
        await log.get(q=MARKER)
    finally:
        logger.setLevel(level)
    assert MARKER not in " ".join(str(vars(record)) for record in recorded_logs.records)


async def test_the_filters(log: Log) -> None:
    await log.chat()
    await log.chat("Başka bir soru")

    assert (await log.get()).json()["total"] == 2
    assert (await log.get(q="başka bir")).json()["total"] == 1
    assert (await log.get(q="100%")).json()["total"] == 0
    assert (await log.get(purpose="analysis", outcome="ok")).json()["total"] == 2
    assert (await log.get(purpose="dictionary_sync")).json()["total"] == 0
    assert len((await log.get(limit=1)).json()["rows"]) == 1


async def test_bad_filters_are_refused(log: Log) -> None:
    for params in ({"purpose": "yok"}, {"outcome": "yok"}, {"q": "x" * 201}):
        response = await log.get(**params)
        assert (response.status_code, response.json()["detail"]["code"]) == (422, "invalid_filter")


async def test_only_managers_can_read_and_only_their_tenant(log: Log) -> None:
    await log.chat()
    row = (await log.get()).json()["rows"][0]

    assert (await log.get(who=log.user)).status_code == 403
    assert (await log.get(f"/{row['public_id']}", who=log.user)).status_code == 403
    assert (await log.auth.client.get(log.url)).status_code == 401

    other = await _sql(
        "INSERT INTO tenant (public_id, code, name) "
        "VALUES (gen_random_uuid()::text, :code, :name) RETURNING tenant_id",
        code="diger-kiraci",
        name=f"Diğer {MARKER}",
    )
    try:
        await _sql(
            "UPDATE llm_call_log SET tenant_id = :id WHERE public_id = :row",
            id=other[0][0],
            row=row["public_id"],
        )
        assert (await log.get()).json()["total"] == 0
        assert (await log.get(f"/{row['public_id']}")).status_code == 404
    finally:
        await _sql("DELETE FROM llm_call_log")
        await _sql("DELETE FROM tenant WHERE tenant_id = :id", id=other[0][0])


async def test_rows_past_the_retention_period_are_removed(log: Log) -> None:
    await log.chat()
    await _sql(
        "UPDATE llm_call_log SET started_at = :old", old=datetime.now(UTC) - timedelta(days=8)
    )
    await log.chat()
    assert (await log.get()).json()["total"] == 1


async def test_a_failed_write_does_not_fail_the_call(log: Log) -> None:
    log.adapter.set_call_log(LlmCallLogWriter(_broken_factory, days=7))  # type: ignore[arg-type]
    assert (await log.chat()).ok


def _broken_factory() -> Any:
    raise RuntimeError(MARKER)


async def test_without_a_sink_nothing_is_kept(log: Log) -> None:
    log.adapter.set_call_log(None)
    assert (await log.chat()).ok
    assert (await log.get()).json()["total"] == 0
