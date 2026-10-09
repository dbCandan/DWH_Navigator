"""The parity fake analyst behind a real-TCP OpenAI-compatible fake server.

Chat requests are answered by ``tests.parity.fake_model.FakeAnalyst`` from the system and user
messages and the response schema the adapter sent, so an analysis job over HTTP gets the replies
the parity test gives the engine in process. ``hold`` makes chat requests wait (a model that
answers slowly or never); ``models`` answers ``GET /models``.
"""

import asyncio
import json
from typing import Any

from tests.fakes.llm_server import (
    FakeLlmServer,
    RecordedRequest,
    Writer,
    chat_reply,
    json_response,
    models_reply,
)
from tests.parity.fake_model import MODEL, NORMAL, FakeAnalyst


class AnalystServer:
    def __init__(self, server: FakeLlmServer) -> None:
        self.fake = server
        self.analyst = FakeAnalyst()
        self.hold: asyncio.Event | None = None
        self.chat_started = asyncio.Event()
        self.reply_marker = ""
        self.down = False
        server.scenario = self._answer

    def ask(self, query: str, scenario: str = NORMAL) -> None:
        self.analyst.begin(query, scenario)

    async def _answer(self, request: RecordedRequest, reader: Any, writer: Writer) -> None:
        if request.method == "GET":
            if self.down:
                writer.write(json_response({"error": "kapalı"}, 500))
            else:
                writer.write(models_reply(MODEL))
            await writer.drain()
            return
        self.chat_started.set()
        if self.hold is not None:
            waiting = asyncio.ensure_future(self.hold.wait())
            closed = asyncio.ensure_future(reader.read(1))
            done, _ = await asyncio.wait({waiting, closed}, return_when=asyncio.FIRST_COMPLETED)
            for task in (waiting, closed):
                task.cancel()
            if closed in done:
                return  # the client went away
        body = request.json()
        messages = body["messages"]
        system = messages[0]["content"]
        user = messages[1]["content"]
        schema = body["response_format"]["json_schema"]["schema"]
        reply, failure = self.analyst.reply(system, user, schema, int(body["max_tokens"]))
        if reply is None:
            writer.write(json_response({"error": failure}, 500))
        else:
            content = json.dumps(reply, ensure_ascii=False)
            if self.reply_marker and "summary" in reply:
                content = content.replace('"summary": "', f'"summary": "{self.reply_marker} ', 1)
            writer.write(chat_reply(content, prompt_tokens=1200, completion_tokens=300))
        await writer.drain()

    @property
    def endpoint(self) -> str:
        return self.fake.url()

    def chat_requests(self) -> list[RecordedRequest]:
        return [r for r in self.fake.requests if r.method == "POST"]
