"""Shared setup of the question analysis and analysis record integration tests.

The real application on a real HTTP server (uvicorn on a free local port, so live streams are
read as they come), PostgreSQL, the synthetic dictionary imported through the API, an active chat
model on a real-TCP fake server answered by the parity fake analyst, and the process's analysis jobs
rebuilt for each test with short time limits.
"""

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import uvicorn

from app.db.session import async_session_factory
from app.infrastructure.llm.openai_adapter import LlmTimeouts, OpenAICompatibleAdapter
from app.main import app
from app.services.analysis.jobs import AnalysisJobs
from app.services.analysis.saved_answers import SavedAnswers
from app.services.answer_feedback import AnswerVotes
from app.services.llm_connections import ConnectionKeys, LlmGateway
from tests.fakes.analyst_server import AnalystServer
from tests.fakes.llm_server import FakeLlmServer
from tests.integration.conftest import SignedIn
from tests.integration.data_dictionary import SYNTHETIC_WORKBOOK, DataDictionary, sql

FAST = LlmTimeouts(connect=2.0, health=1.0, model_list=1.0, model_list_budget=1.5)
FINAL = ("completed", "failed", "cancelled", "interrupted")


async def local_resolver(host: str, port: int) -> list[str]:
    return ["127.0.0.1"]


async def reset_analyses() -> None:
    await sql("DELETE FROM answer_vote")
    await sql("DELETE FROM saved_answer")
    await sql("DELETE FROM analysis_record")
    await sql("DELETE FROM llm_integration")


@dataclass
class Sse:
    """One event read from a live stream."""

    id: int | None
    data: dict[str, Any] | None
    comment: str | None = None


@dataclass
class Live:
    """A live progress stream being read in the background."""

    response: httpx.Response
    events: list[Sse] = field(default_factory=list)
    task: asyncio.Task[None] | None = None
    closed: asyncio.Event = field(default_factory=asyncio.Event)

    def types(self) -> list[str]:
        return [str(e.data["type"]) for e in self.events if e.data is not None]

    def comments(self) -> list[str]:
        return [e.comment for e in self.events if e.comment is not None]

    async def wait_for(self, kind: str, timeout: float = 10.0) -> None:
        async with asyncio.timeout(timeout):
            while kind not in self.types():
                if self.closed.is_set():
                    raise AssertionError(f"stream closed before {kind}: {self.types()}")
                await asyncio.sleep(0.02)

    async def wait_closed(self, timeout: float = 10.0) -> None:
        async with asyncio.timeout(timeout):
            await self.closed.wait()


async def _read(live: Live) -> None:
    current: dict[str, str] = {}
    try:
        async for line in live.response.aiter_lines():
            if line.startswith(":"):
                live.events.append(Sse(None, None, line[1:].strip()))
            elif line.startswith("id: "):
                current["id"] = line[4:]
            elif line.startswith("data: "):
                current["data"] = line[6:]
            elif line == "" and current:
                live.events.append(Sse(int(current["id"]), json.loads(current["data"])))
                current = {}
    except (httpx.ReadError, httpx.RemoteProtocolError, asyncio.CancelledError):
        pass
    finally:
        live.closed.set()


@dataclass
class Qa:
    dd: DataDictionary
    http: httpx.AsyncClient
    model: AnalystServer
    adapter: OpenAICompatibleAdapter
    gateway: LlmGateway
    jobs: AnalysisJobs
    user: SignedIn
    other: SignedIn
    streams: list[Live] = field(default_factory=list)

    @property
    def prefix(self) -> str:
        return self.dd.auth.prefix

    def headers(self, who: SignedIn | None = None) -> dict[str, str]:
        return {**self.dd.auth.headers(who or self.user), **self.dd.auth.origin()}

    async def request(
        self, method: str, path: str, who: SignedIn | None = None, **kwargs: Any
    ) -> httpx.Response:
        headers = {**self.headers(who), **kwargs.pop("headers", {})}
        return await self.http.request(method, f"{self.prefix}{path}", headers=headers, **kwargs)

    async def start(self, query: str, who: SignedIn | None = None, **body: Any) -> httpx.Response:
        self.model.ask(query)
        return await self.request("POST", "/analyses", who, json={"query": query, **body})

    async def started(self, query: str, who: SignedIn | None = None, **body: Any) -> str:
        response = await self.start(query, who, **body)
        assert response.status_code == 202, response.text
        return str(response.json()["analysis_id"])

    async def job(self, analysis_id: str, who: SignedIn | None = None) -> dict[str, Any]:
        response = await self.request("GET", f"/analyses/{analysis_id}", who)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    async def finished(
        self, analysis_id: str, who: SignedIn | None = None, timeout: float = 30.0
    ) -> dict[str, Any]:
        async with asyncio.timeout(timeout):
            while True:
                body = await self.job(analysis_id, who)
                if body["state"] in FINAL:
                    return body
                await asyncio.sleep(0.05)

    async def follow(
        self,
        analysis_id: str,
        who: SignedIn | None = None,
        last_event_id: int | None = None,
        token: str | None = None,
    ) -> Live:
        headers = self.headers(who)
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = self.http.build_request(
            "GET", f"{self.prefix}/analyses/{analysis_id}/events", headers=headers
        )
        response = await self.http.send(request, stream=True)
        live = Live(response)
        if response.status_code == 200:
            live.task = asyncio.create_task(_read(live))
        else:
            await response.aread()
            live.closed.set()
        self.streams.append(live)
        return live

    async def close_streams(self) -> None:
        for live in self.streams:
            if live.task is not None:
                live.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await live.task
            await live.response.aclose()


async def connect_model(dd: DataDictionary, endpoint: str) -> None:
    admin = dd.admin
    response = await dd.auth.client.post(
        f"{dd.auth.prefix}/llm-integrations",
        json={
            "name": "Deneme sunucusu",
            "endpoint": endpoint,
            "chat_model": "fake-analyst",
            "activate": True,
        },
        headers=dd.auth.headers(admin),
    )
    assert response.status_code == 201, response.text


@contextlib.asynccontextmanager
async def live_server() -> AsyncIterator[str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="off", log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    async with asyncio.timeout(10):
        while not server.started:
            await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def qa_harness(
    dd: DataDictionary,
    *,
    connect: bool = True,
    import_dictionary: bool = True,
    **job_options: Any,
) -> AsyncIterator[Qa]:
    await reset_analyses()
    dd.auth.use_settings(environment="development")
    if import_dictionary:
        imported = await dd.import_dictionary(SYNTHETIC_WORKBOOK.read_bytes())
        assert imported.status_code in (200, 201), imported.text
    fake = await FakeLlmServer().start()
    model = AnalystServer(fake)
    adapter = OpenAICompatibleAdapter(
        ca_bundle="", max_concurrent_calls=2, resolver=local_resolver, timeouts=FAST
    )
    settings = dd.auth.settings
    gateway = LlmGateway(
        port=adapter,
        session_factory=async_session_factory,
        keys=lambda: ConnectionKeys(settings),
    )
    if connect:
        await connect_model(dd, model.endpoint)
    options: dict[str, Any] = {"keepalive_seconds": 15.0} | job_options
    saved_answers = SavedAnswers(async_session_factory)
    votes = AnswerVotes(
        index=dd.index, session_factory=async_session_factory, saved_answers=saved_answers
    )
    jobs = AnalysisJobs(
        index=dd.index,
        models=gateway,
        session_factory=async_session_factory,
        saved_answers=saved_answers,
        overlay=votes,
        **options,
    )
    previous = app.state.analysis_jobs, app.state.answer_votes
    app.state.analysis_jobs, app.state.answer_votes = jobs, votes
    user = await dd.auth.account(dd.admin, "kullanici")
    other = await dd.auth.account(dd.admin, "kullanici")
    try:
        async with live_server() as base, httpx.AsyncClient(base_url=base, timeout=30.0) as http:
            qa = Qa(dd, http, model, adapter, gateway, jobs, user, other)
            try:
                yield qa
            finally:
                await qa.close_streams()
                if model.hold is not None:
                    model.hold.set()
                await jobs.shutdown(wait_seconds=5.0)
    finally:
        app.state.analysis_jobs, app.state.answer_votes = previous
        await fake.close()


async def record(analysis_id: str) -> dict[str, Any]:
    rows = await sql("SELECT * FROM analysis_record WHERE public_id = :p", p=analysis_id)
    assert rows, analysis_id
    return dict(rows[0]._mapping)


def elapsed_since(started: float) -> float:
    return time.monotonic() - started


async def saved_answer_count() -> int:
    ((count,),) = await sql("SELECT count(*) FROM saved_answer")
    return int(count)
