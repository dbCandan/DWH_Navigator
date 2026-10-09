"""The httpx model adapter against a real-TCP fake server (data-dictionary 003-llm-connection).

Requirement 6-12 and 14, 17 and 18 (Acceptance 2-4): the request body bytes, feature adaptation
and its memory, the repair request, the failure classes, TLS and the private-network policy, no
proxy and no redirect, the response limit, cancellation, the health check and its cache, model
lists, the slot limit, the content-free summary, and the Gözlemlenebilirlik signal names, label
sets and span attributes.
"""

import asyncio
import json
import logging
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpcore
import pytest

from app.core.logging import JsonFormatter
from app.domain.llm import (
    MAX_RESPONSE_BYTES,
    REPAIR_PROMPT,
    USER_AGENT,
    AdaptedFeature,
    LlmChatRequest,
    LlmConnection,
    LlmOutcome,
    LlmPurpose,
)
from app.infrastructure.llm.network import (
    NetworkPolicyDenied,
    PrivateNetworkBackend,
    is_private_address,
)
from app.infrastructure.llm.openai_adapter import (
    LlmTimeouts,
    OpenAICompatibleAdapter,
    RequestFeatures,
    chat_body,
)
from tests.fakes.cancel import CancelToken
from tests.fakes.llm_server import (
    HOST_NAME,
    FakeLlmServer,
    RecordedRequest,
    ServerPki,
    Writer,
    chat_reply,
    hang,
    http_response,
    json_response,
    models_reply,
    respond,
    script,
    write_pki,
)
from tests.fakes.telemetry import TelemetryCapture

pytestmark = pytest.mark.unit

MARKER = f"ISARET-{uuid4().hex}"
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
FAST = LlmTimeouts(
    connect=1.0,
    health=0.5,
    model_list=0.4,
    model_list_budget=0.6,
    lm_studio=0.2,
    inventory=0.3,
    inventory_server_budget=0.5,
    inventory_budget=1.2,
    test_chat=0.4,
    test_chat_budget=0.6,
)


async def private_resolver(host: str, port: int) -> list[str]:
    assert host == HOST_NAME
    return ["127.0.0.1"]


@pytest.fixture
def pki(tmp_path: Path) -> ServerPki:
    return write_pki(tmp_path / "pki")


@pytest.fixture
async def server() -> AsyncIterator[FakeLlmServer]:
    fake = await FakeLlmServer().start()
    try:
        yield fake
    finally:
        await fake.close()


@pytest.fixture
async def tls_server(pki: ServerPki) -> AsyncIterator[FakeLlmServer]:
    fake = await FakeLlmServer(pki).start()
    try:
        yield fake
    finally:
        await fake.close()


class LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def events(self, name: str) -> list[dict[str, Any]]:
        return [
            dict(getattr(record, "structured_fields", {}))
            for record in self.records
            if record.getMessage() == name
        ]

    def rendered(self) -> str:
        formatter = JsonFormatter()
        return "\n".join(formatter.format(record) for record in self.records)


@pytest.fixture
def logs() -> Iterator[LogCapture]:
    # Every record at every level, so a library that logs the request URL would be caught.
    handler = LogCapture()
    logger = logging.getLogger("app.llm")
    level = logger.level
    logger.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(root_level)
        logger.setLevel(level)


def adapter(
    *,
    ca: ServerPki | None = None,
    limit: int = 2,
    resolver: Any = private_resolver,
    timeouts: LlmTimeouts = FAST,
    clock: Any = time.monotonic,
) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        ca_bundle=str(ca.ca_path) if ca is not None else "",
        max_concurrent_calls=limit,
        resolver=resolver,
        timeouts=timeouts,
        clock=clock,
    )


def connection(server: FakeLlmServer, **overrides: Any) -> LlmConnection:
    values: dict[str, Any] = {
        "endpoint": server.url(),
        "chat_model": "deneme-model",
        "timeout_seconds": 5,
        "public_id": str(uuid4()),
    }
    values.update(overrides)
    return LlmConnection(**values)


def ask(
    purpose: LlmPurpose = LlmPurpose.ANALYSIS, *, user: str = "soru", max_tokens: int = 2500
) -> LlmChatRequest:
    return LlmChatRequest(
        system="Sistem istemi ŞİĞ",
        user=user,
        schema=SCHEMA,
        max_tokens=max_tokens,
        purpose=purpose,
    )


def refusal(text: str) -> bytes:
    return json_response({"error": {"message": text}}, status=400)


# --- Requirement 6: the request -----------------------------------------------------------------


def test_the_body_is_written_exactly_as_the_source_writes_it() -> None:
    features = RequestFeatures(True, True, "none", 42)
    body = chat_body(
        model="gemma-4-31b",
        messages=[
            {"role": "system", "content": "SİSTEM"},
            {"role": "user", "content": "müşteri"},
        ],
        system="SİSTEM",
        temperature=0.0,
        max_tokens=2500,
        schema={"type": "object", "required": ["a"]},
        features=features,
    )
    assert body == (
        b'{"model": "gemma-4-31b", "messages": [{"role": "system", "content": "S\\u0130STEM"}, '
        b'{"role": "user", "content": "m\\u00fc\\u015fteri"}], "temperature": 0.0, '
        b'"max_tokens": 2500, "reasoning_effort": "none", "seed": 42, "response_format": '
        b'{"type": "json_schema", "json_schema": {"name": "result", "strict": true, "schema": '
        b'{"type": "object", "required": ["a"]}}}}'
    )
    folded = chat_body(
        model="m",
        messages=[
            {"role": "system", "content": "S"},
            {"role": "user", "content": "U"},
            {"role": "assistant", "content": "A"},
        ],
        system="S",
        temperature=0.7,
        max_tokens=60,
        schema={},
        features=RequestFeatures(False, False, "", None),
    )
    assert folded == (
        b'{"model": "m", "messages": [{"role": "user", "content": "S\\n\\nU"}, '
        b'{"role": "assistant", "content": "A"}], "temperature": 0.7, "max_tokens": 60}'
    )
    thinking_off = chat_body(
        model="m",
        messages=[{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
        system="S",
        temperature=0.0,
        max_tokens=60,
        schema={},
        features=RequestFeatures(True, False, "", 42, thinking_off=True),
    )
    assert thinking_off == (
        b'{"model": "m", "messages": [{"role": "system", "content": "S"}, '
        b'{"role": "user", "content": "U"}], "temperature": 0.0, "max_tokens": 60, '
        b'"chat_template_kwargs": {"enable_thinking": false}, "seed": 42}'
    )


async def test_a_chat_call_posts_the_body_and_returns_the_object(server: FakeLlmServer) -> None:
    server.scenario = respond(chat_reply('```json\n{"ok": true}\n```'))
    target = connection(server)

    result = await adapter().chat(target, ask())

    assert result.ok and result.value == {"ok": True}
    (request,) = server.requests
    assert (request.method, request.path) == ("POST", "/v1/chat/completions")
    assert request.headers["content-type"] == "application/json"
    assert request.headers["user-agent"] == USER_AGENT
    assert "authorization" not in request.headers
    assert request.body == chat_body(
        model="deneme-model",
        messages=[
            {"role": "system", "content": "Sistem istemi ŞİĞ"},
            {"role": "user", "content": "soru"},
        ],
        system="Sistem istemi ŞİĞ",
        temperature=0.0,
        max_tokens=2500,
        schema=SCHEMA,
        features=RequestFeatures(True, True, "none", 42),
    )
    summary = result.summary
    assert (summary.outcome, summary.http_status, summary.requests, summary.repaired) == (
        LlmOutcome.OK,
        200,
        1,
        False,
    )
    assert (summary.prompt_tokens, summary.completion_tokens) == (11, 7)
    assert summary.integration_public_id == target.public_id
    assert summary.purpose is LlmPurpose.ANALYSIS and summary.model == "deneme-model"


async def test_the_key_goes_only_as_a_bearer_header(server: FakeLlmServer) -> None:
    server.scenario = respond(chat_reply('{"ok": true}'))
    key = f"anahtar-{uuid4().hex}"
    await adapter().chat(connection(server, api_key=key), ask())
    assert server.requests[0].headers["authorization"] == f"Bearer {key}"
    assert key.encode() not in server.requests[0].body


async def test_seed_minus_one_and_an_empty_effort_are_not_sent(server: FakeLlmServer) -> None:
    server.scenario = respond(chat_reply('{"ok": true}'))
    await adapter().chat(connection(server, seed=-1, reasoning_effort=""), ask())
    sent = server.requests[0].json()
    assert list(sent) == ["model", "messages", "temperature", "max_tokens", "response_format"]


# --- Requirement 7 and 8: adaptation and repair -------------------------------------------------


async def test_refused_features_are_dropped_in_order_and_remembered(
    server: FakeLlmServer,
) -> None:
    server.scenario = script(
        [
            refusal("Developer instruction is not enabled for model"),
            refusal("JSON mode is not enabled for model"),
            refusal("reasoning_effort is not supported"),
            chat_reply('{"ok": true}'),
            chat_reply('{"ok": false}'),
        ]
    )
    chat = adapter()
    target = connection(server)

    first = await chat.chat(target, ask())
    second = await chat.chat(target, ask(user="soru 2"))

    assert first.value == {"ok": True} and second.value == {"ok": False}
    assert first.summary.adaptations == (
        AdaptedFeature.SYSTEM_ROLE,
        AdaptedFeature.RESPONSE_FORMAT,
        AdaptedFeature.REASONING_EFFORT,
    )
    assert first.summary.requests == 4
    assert second.summary.requests == 1 and second.summary.adaptations == ()
    last = json.loads(server.chat_bodies()[-1])
    assert last["messages"] == [{"role": "user", "content": "Sistem istemi ŞİĞ\n\nsoru 2"}]
    assert "response_format" not in last and "reasoning_effort" not in last
    assert last["seed"] == 42
    # The refused "none" turned thinking off through the chat template (rule 3, target only).
    assert last["chat_template_kwargs"] == THINKING_OFF


async def test_a_changed_connection_forgets_what_was_learned(server: FakeLlmServer) -> None:
    server.scenario = script(
        [
            refusal("unsupported parameter: seed"),
            chat_reply('{"ok": true}'),
            chat_reply('{"ok": true}'),
        ]
    )
    chat = adapter()
    target = connection(server)
    await chat.chat(target, ask())
    changed = replace(target, temperature=0.2)
    await chat.chat(changed, ask())
    bodies = [json.loads(body) for body in server.chat_bodies()]
    assert [("seed" in body) for body in bodies] == [True, False, True]


async def test_a_connection_test_starts_fresh_and_teaches_nothing(server: FakeLlmServer) -> None:
    server.scenario = script(
        [
            refusal("unsupported parameter: seed"),
            chat_reply('{"cevap": "Ankara"}'),
            chat_reply('{"ok": true}'),
        ]
    )
    chat = adapter()
    target = connection(server)
    tested = await chat.chat(target, ask(LlmPurpose.CONNECTION_TEST, max_tokens=60))
    assert tested.summary.adaptations == (AdaptedFeature.SEED,)
    await chat.chat(target, ask())
    assert "seed" in json.loads(server.chat_bodies()[-1])


async def test_at_most_three_features_are_dropped_in_one_call(server: FakeLlmServer) -> None:
    server.scenario = script(
        [
            refusal("system instruction unsupported"),
            refusal("schema unsupported"),
            refusal("thinking unsupported"),
            refusal("seed unsupported"),
        ]
    )
    result = await adapter().chat(connection(server), ask())
    assert result.outcome is LlmOutcome.UPSTREAM_STATUS and result.http_status == 400
    assert result.summary.requests == 4 and len(result.summary.adaptations) == 3


# vLLM's refusal of ``reasoning_effort: "none"`` (it accepts only low, medium and high).
VLLM_EFFORT_REFUSAL = (
    "[{'type': 'literal_error', 'loc': ('body', 'reasoning_effort'), "
    "'msg': \"Input should be 'low', 'medium' or 'high'\", 'input': 'none'}]"
)
THINKING_OFF = {"enable_thinking": False}


async def test_a_refused_none_effort_is_resent_with_thinking_off_and_remembered(
    server: FakeLlmServer, logs: LogCapture
) -> None:
    server.scenario = script(
        [
            refusal(f"{VLLM_EFFORT_REFUSAL} {MARKER}"),
            chat_reply('\n\n{"ok": true}'),
            chat_reply('{"ok": false}'),
        ]
    )
    chat = adapter()
    target = connection(server)

    first = await chat.chat(target, ask())
    second = await chat.chat(target, ask(user="soru 2"))

    assert first.value == {"ok": True} and second.value == {"ok": False}
    assert first.summary.adaptations == (AdaptedFeature.REASONING_EFFORT,)
    assert first.summary.requests == 2
    # Remembered for the connection: the next call pays no second refusal.
    assert second.summary.requests == 1 and second.summary.adaptations == ()
    bodies = server.chat_bodies()
    # The first request is the source's, byte for byte.
    assert bodies[0] == chat_body(
        model="deneme-model",
        messages=[
            {"role": "system", "content": "Sistem istemi ŞİĞ"},
            {"role": "user", "content": "soru"},
        ],
        system="Sistem istemi ŞİĞ",
        temperature=0.0,
        max_tokens=2500,
        schema=SCHEMA,
        features=RequestFeatures(True, True, "none", 42),
    )
    for body in bodies[1:]:
        sent = json.loads(body)
        assert list(sent) == [
            "model",
            "messages",
            "temperature",
            "max_tokens",
            "chat_template_kwargs",
            "seed",
            "response_format",
        ]
        assert sent["chat_template_kwargs"] == THINKING_OFF
        assert b'"chat_template_kwargs": {"enable_thinking": false}, "seed": 42' in body
    # Neither the server's refusal nor the reply reaches the log.
    assert MARKER not in logs.rendered()
    assert "literal_error" not in logs.rendered() and "enable_thinking" not in logs.rendered()


async def test_a_refused_thinking_switch_is_dropped_and_remembered(
    server: FakeLlmServer,
) -> None:
    server.scenario = script(
        [
            refusal(VLLM_EFFORT_REFUSAL),
            refusal("Unrecognized request argument supplied: chat_template_kwargs"),
            chat_reply('{"ok": true}'),
            chat_reply('{"ok": false}'),
        ]
    )
    chat = adapter()
    target = connection(server)

    first = await chat.chat(target, ask())
    second = await chat.chat(target, ask(user="soru 2"))

    assert first.ok and second.ok
    assert first.summary.adaptations == (
        AdaptedFeature.REASONING_EFFORT,
        AdaptedFeature.CHAT_TEMPLATE_KWARGS,
    )
    assert second.summary.requests == 1 and second.summary.adaptations == ()
    bodies = [json.loads(body) for body in server.chat_bodies()]
    assert [("chat_template_kwargs" in body) for body in bodies] == [False, True, False, False]
    assert [("reasoning_effort" in body) for body in bodies] == [True, False, False, False]


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
async def test_a_refused_effort_other_than_none_is_only_dropped(
    server: FakeLlmServer, effort: str
) -> None:
    server.scenario = script([refusal("reasoning_effort is not supported"), chat_reply("{}")])
    result = await adapter().chat(connection(server, reasoning_effort=effort), ask())
    assert result.ok and result.summary.adaptations == (AdaptedFeature.REASONING_EFFORT,)
    first, resent = (json.loads(body) for body in server.chat_bodies())
    assert first["reasoning_effort"] == effort
    assert "reasoning_effort" not in resent and "chat_template_kwargs" not in resent


@pytest.mark.parametrize("effort", ["none", "low", "medium", "high", ""])
async def test_an_accepted_first_request_never_carries_the_thinking_switch(
    server: FakeLlmServer, effort: str
) -> None:
    server.scenario = respond(chat_reply('{"ok": true}'))
    await adapter().chat(connection(server, reasoning_effort=effort), ask())
    (request,) = server.requests
    assert b"chat_template_kwargs" not in request.body
    assert ("reasoning_effort" in request.json()) is bool(effort)


async def test_a_connection_test_turns_thinking_off_without_teaching_analyses(
    server: FakeLlmServer,
) -> None:
    server.scenario = script(
        [
            refusal(VLLM_EFFORT_REFUSAL),
            chat_reply('\n\n{"cevap": "Ankara"}'),
            chat_reply('{"ok": true}'),
        ]
    )
    chat = adapter()
    target = connection(server)
    tested = await chat.chat(target, ask(LlmPurpose.CONNECTION_TEST, max_tokens=60))
    assert tested.value == {"cevap": "Ankara"}
    await chat.chat(target, ask())
    last = json.loads(server.chat_bodies()[-1])
    assert last["reasoning_effort"] == "none" and "chat_template_kwargs" not in last


async def test_one_repair_then_invalid_json(server: FakeLlmServer) -> None:
    first = "Tabii, işte cevap: " + "x" * 2500
    server.scenario = script(
        [
            chat_reply(first, prompt_tokens=100, completion_tokens=20),
            chat_reply("yine düz metin", prompt_tokens=150, completion_tokens=5),
        ]
    )
    result = await adapter().chat(connection(server), ask())
    assert result.outcome is LlmOutcome.INVALID_JSON and result.value is None
    assert result.summary.repaired and result.summary.requests == 2
    assert (result.summary.prompt_tokens, result.summary.completion_tokens) == (250, 25)
    messages = json.loads(server.chat_bodies()[1])["messages"]
    assert messages[2:] == [
        {"role": "assistant", "content": first[:2000]},
        {"role": "user", "content": REPAIR_PROMPT},
    ]


async def test_a_repaired_reply_is_returned(server: FakeLlmServer) -> None:
    server.scenario = script([chat_reply("hmm"), chat_reply('<think>x</think>{"ok": true}')])
    result = await adapter().chat(connection(server), ask())
    assert result.ok and result.value == {"ok": True} and result.summary.repaired


# --- Requirement 9, 10 and 13: failure classes --------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "outcome", "status"),
    [
        (json_response({"error": "invalid api key"}, 401), LlmOutcome.UNAUTHORIZED, 401),
        (json_response({"error": "forbidden"}, 403), LlmOutcome.UNAUTHORIZED, 403),
        (json_response({"error": "boom"}, 500), LlmOutcome.UPSTREAM_STATUS, 500),
        (json_response({"error": "gateway"}, 504), LlmOutcome.UPSTREAM_STATUS, 504),
        (
            refusal("This model's maximum context length is 65536 tokens"),
            LlmOutcome.CONTEXT_EXCEEDED,
            400,
        ),
        (
            json_response({"error": "request exceeds the context size"}, 500),
            LlmOutcome.CONTEXT_EXCEEDED,
            500,
        ),
        (refusal("bilinmeyen alan"), LlmOutcome.UPSTREAM_STATUS, 400),
        (http_response(200, b"<html>vekil</html>"), LlmOutcome.INVALID_RESPONSE, 200),
        (json_response([1, 2]), LlmOutcome.INVALID_RESPONSE, 200),
        (json_response({"id": "x"}), LlmOutcome.INVALID_RESPONSE, 200),
        (json_response({"choices": []}), LlmOutcome.INVALID_RESPONSE, 200),
        (json_response({"choices": [{"message": "x"}]}), LlmOutcome.INVALID_RESPONSE, 200),
    ],
)
async def test_failures_map_to_fixed_classes(
    server: FakeLlmServer, payload: bytes, outcome: LlmOutcome, status: int
) -> None:
    server.scenario = respond(payload)
    result = await adapter().chat(connection(server), ask())
    assert (result.outcome, result.http_status) == (outcome, status)
    assert result.summary.requests == 1 and not result.summary.repaired


async def test_a_redirect_is_not_followed(server: FakeLlmServer) -> None:
    server.scenario = respond(
        http_response(307, b"", extra=f"Location: {server.url('/elsewhere')}\r\n")
    )
    result = await adapter().chat(connection(server), ask())
    assert (result.outcome, result.http_status) == (LlmOutcome.UPSTREAM_STATUS, 307)
    assert len(server.requests) == 1


async def test_a_response_over_four_mebibytes_is_cut(server: FakeLlmServer) -> None:
    async def huge(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        size = MAX_RESPONSE_BYTES + 10
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {size}\r\nConnection: close\r\n\r\n".encode()
        )
        piece = b" " * 65536
        sent = 0
        while sent < size:
            writer.write(piece[: size - sent])
            sent += len(piece)
            await writer.drain()

    server.scenario = huge
    result = await adapter().chat(connection(server), ask())
    assert result.outcome is LlmOutcome.RESPONSE_TOO_LARGE


async def test_a_hanging_server_times_out_without_retry(server: FakeLlmServer) -> None:
    server.scenario = hang()
    started = time.monotonic()
    result = await adapter().chat(connection(server, timeout_seconds=1), ask())
    assert result.outcome is LlmOutcome.TIMEOUT
    assert time.monotonic() - started < 3
    assert len(server.requests) == 1


async def test_a_refused_connection_is_not_retried() -> None:
    closed = await FakeLlmServer().start()
    await closed.close()
    result = await adapter().chat(connection(closed), ask())
    assert result.outcome is LlmOutcome.CONNECT_REFUSED and result.summary.requests == 1


async def test_an_untrusted_certificate_is_a_tls_error_and_no_body_arrives(
    pki: ServerPki, tmp_path: Path
) -> None:
    impostor = await FakeLlmServer(pki).start(certificate=write_pki(tmp_path / "impostor"))
    impostor.scenario = respond(chat_reply('{"ok": true}'))
    try:
        result = await adapter(ca=pki).chat(connection(impostor), ask())
    finally:
        await impostor.close()
    assert result.outcome is LlmOutcome.TLS_ERROR
    assert impostor.requests == []


async def test_a_trusted_certificate_with_the_host_name_works(tls_server: FakeLlmServer) -> None:
    tls_server.scenario = respond(chat_reply('{"ok": true}'))
    assert tls_server.pki is not None
    result = await adapter(ca=tls_server.pki).chat(connection(tls_server), ask())
    assert result.ok


async def test_a_public_address_is_denied_before_any_connection(
    tls_server: FakeLlmServer,
) -> None:
    async def public(host: str, port: int) -> list[str]:
        return ["127.0.0.1", "93.184.216.34"]

    assert tls_server.pki is not None
    result = await adapter(ca=tls_server.pki, resolver=public).chat(connection(tls_server), ask())
    assert result.outcome is LlmOutcome.NETWORK_POLICY_DENIED
    assert tls_server.connections == 0 and tls_server.requests == []


async def test_a_public_literal_address_is_denied() -> None:
    target = LlmConnection(endpoint="http://8.8.8.8:80/v1", chat_model="m", timeout_seconds=5)
    result = await adapter().chat(target, ask())
    assert result.outcome is LlmOutcome.NETWORK_POLICY_DENIED


async def test_an_address_that_changes_at_connect_time_is_denied(
    tls_server: FakeLlmServer,
) -> None:
    answers = iter([["127.0.0.1"], ["93.184.216.34"]])

    async def rebinding(host: str, port: int) -> list[str]:
        return next(answers)

    assert tls_server.pki is not None
    chat = adapter(ca=tls_server.pki, resolver=rebinding)
    assert await chat.check_address(tls_server.url()) is LlmOutcome.OK
    result = await chat.chat(connection(tls_server), ask())
    assert result.outcome is LlmOutcome.NETWORK_POLICY_DENIED
    assert tls_server.connections == 0 and tls_server.requests == []


async def test_an_unresolvable_name_is_its_own_class(tls_server: FakeLlmServer) -> None:
    async def missing(host: str, port: int) -> list[str]:
        raise socket.gaierror(socket.EAI_NONAME, "not known")

    assert tls_server.pki is not None
    chat = adapter(ca=tls_server.pki, resolver=missing)
    assert (await chat.chat(connection(tls_server), ask())).outcome is LlmOutcome.NAME_UNRESOLVED
    assert await chat.check_address(tls_server.url()) is LlmOutcome.NAME_UNRESOLVED


class _PublicPeerStream(httpcore.AsyncNetworkStream):
    closed = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        raise AssertionError("no byte may be read")

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        raise AssertionError("no byte may be written")

    async def aclose(self) -> None:
        self.closed = True

    def get_extra_info(self, info: str) -> Any:
        return ("198.51.100.7", 443) if info == "server_addr" else None


class _PublicPeerBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.stream = _PublicPeerStream()

    async def connect_tcp(self, host: str, port: int, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        return self.stream

    async def connect_unix_socket(self, path: str, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        raise AssertionError

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


async def test_the_connected_peer_address_is_checked_too() -> None:
    inner = _PublicPeerBackend()
    backend = PrivateNetworkBackend(private_resolver, inner)
    with pytest.raises(NetworkPolicyDenied):
        await backend.connect_tcp(HOST_NAME, 443, timeout=1)
    assert inner.stream.closed


@pytest.mark.parametrize(
    ("address", "private"),
    [
        ("10.1.2.3", True),
        ("172.31.0.1", True),
        ("192.168.5.5", True),
        ("127.0.0.1", True),
        ("169.254.1.1", True),
        ("100.64.0.1", True),
        ("::1", True),
        ("fe80::1%eth0", True),
        ("fd12::1", True),
        ("::ffff:10.0.0.1", True),
        ("::ffff:8.8.8.8", False),
        ("172.32.0.1", False),
        ("8.8.8.8", False),
        ("2001:db8::1", False),
        ("2002:a00:1::", False),
    ],
)
def test_private_ranges_are_the_policy_ranges(address: str, private: bool) -> None:
    assert is_private_address(address) is private


async def test_proxies_from_the_environment_are_ignored(
    server: FakeLlmServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "HTTP_PROXY", "http_proxy"):
        monkeypatch.setenv(name, "http://10.255.255.1:3128")
    server.scenario = respond(chat_reply('{"ok": true}'))
    result = await adapter().chat(connection(server), ask())
    assert result.ok and len(server.requests) == 1


# --- Requirement 11: stopping -------------------------------------------------------------------


async def test_a_stop_from_another_thread_closes_the_request_within_a_second(
    server: FakeLlmServer,
) -> None:
    started = asyncio.Event()
    server.scenario = hang(started)
    token = CancelToken()
    call = asyncio.create_task(
        adapter().chat(connection(server, timeout_seconds=60), ask(), cancel=token)
    )
    await asyncio.wait_for(started.wait(), 5)
    stopped = time.monotonic()
    threading.Thread(target=token.cancel).start()
    result = await asyncio.wait_for(call, 1)
    assert time.monotonic() - stopped < 1
    assert result.outcome is LlmOutcome.CANCELLED and result.value is None
    assert result.summary.outcome is LlmOutcome.CANCELLED and not result.summary.repaired
    for _ in range(50):
        if server.closed_at:
            break
        await asyncio.sleep(0.01)
    assert server.closed_at and server.closed_at[0] - stopped < 1
    assert len(server.requests) == 1


async def test_a_stopped_analysis_sends_nothing(server: FakeLlmServer) -> None:
    token = CancelToken()
    token.cancel()
    server.scenario = respond(chat_reply('{"ok": true}'))
    result = await adapter().chat(connection(server), ask(), cancel=token)
    assert result.outcome is LlmOutcome.CANCELLED and server.connections == 0


async def test_a_waiting_call_that_is_stopped_never_sends(server: FakeLlmServer) -> None:
    started = asyncio.Event()
    server.scenario = hang(started)
    chat = adapter(limit=1)
    holder_token = CancelToken()
    holder = asyncio.create_task(
        chat.chat(connection(server, timeout_seconds=60), ask(), cancel=holder_token)
    )
    await asyncio.wait_for(started.wait(), 5)
    waiting_token = CancelToken()
    waiting = asyncio.create_task(chat.chat(connection(server), ask(), cancel=waiting_token))
    await asyncio.sleep(0.05)
    waiting_token.cancel()
    assert (await asyncio.wait_for(waiting, 1)).outcome is LlmOutcome.CANCELLED
    holder_token.cancel()
    await asyncio.wait_for(holder, 1)
    assert len(server.requests) == 1


async def test_cancelling_the_caller_records_the_call_and_propagates(
    server: FakeLlmServer, logs: LogCapture
) -> None:
    started = asyncio.Event()
    server.scenario = hang(started)
    call = asyncio.create_task(adapter().chat(connection(server, timeout_seconds=60), ask()))
    await asyncio.wait_for(started.wait(), 5)
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert [event["outcome"] for event in logs.events("llm.call")] == ["cancelled"]


# --- Requirement 17: the process-wide limit -----------------------------------------------------


async def test_five_callers_never_exceed_two_chat_requests(server: FakeLlmServer) -> None:
    async def slow(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        await asyncio.sleep(0.1)
        writer.write(chat_reply('{"ok": true}'))
        await writer.drain()

    server.scenario = slow
    chat = adapter(limit=2)
    results = await asyncio.gather(*(chat.chat(connection(server), ask()) for _ in range(5)))
    assert all(result.ok for result in results)
    assert server.peak == 2 and len(server.requests) == 5
    assert max(result.summary.wait_ms for result in results) >= 150


async def test_model_list_reads_do_not_take_chat_slots(server: FakeLlmServer) -> None:
    started = asyncio.Event()

    async def scenario(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        if request.method == "POST":
            await hang(started)(request, reader, writer)
            return
        writer.write(models_reply("a"))
        await writer.drain()

    server.scenario = scenario
    chat = adapter(limit=1)
    token = CancelToken()
    busy = asyncio.create_task(
        chat.chat(connection(server, timeout_seconds=60), ask(), cancel=token)
    )
    await asyncio.wait_for(started.wait(), 5)
    listing = await chat.list_models(connection(server))
    assert listing.probe.ok and [model.id for model in listing.models] == ["a"]
    token.cancel()
    await busy


# --- Requirement 12: the health check -----------------------------------------------------------


async def test_a_closed_port_is_reported_within_a_second() -> None:
    closed = await FakeLlmServer().start()
    await closed.close()
    started = time.monotonic()
    probe = await adapter(timeouts=LlmTimeouts()).health(connection(closed))
    assert time.monotonic() - started < 1
    assert probe.outcome is LlmOutcome.CONNECT_REFUSED
    assert probe.message.startswith("Model sunucusuna ulaşılamadı: bağlantı reddedildi")


async def test_an_unresponsive_address_is_reported_within_six_seconds(
    server: FakeLlmServer,
) -> None:
    server.scenario = hang()
    started = time.monotonic()
    probe = await adapter(timeouts=LlmTimeouts()).health(connection(server, timeout_seconds=900))
    elapsed = time.monotonic() - started
    assert probe.outcome is LlmOutcome.TIMEOUT
    assert 4.5 < elapsed < 6


async def test_the_health_result_is_shared_for_thirty_seconds(server: FakeLlmServer) -> None:
    server.scenario = respond(models_reply("baska-model"))
    now = [1000.0]
    chat = adapter(clock=lambda: now[0], timeouts=LlmTimeouts())
    target = connection(server, api_key="k-1")

    first = await chat.health(target)
    now[0] += 29
    second = await chat.health(target)
    assert first.ok and not first.cached  # the chat model need not be listed
    assert second.ok and second.cached and len(server.requests) == 1
    assert server.requests[0].headers["authorization"] == "Bearer k-1"

    changed = LlmConnection(
        endpoint=target.endpoint, chat_model="m2", api_key="k-1", public_id=target.public_id
    )
    assert not (await chat.health(changed)).cached and len(server.requests) == 2
    now[0] += 31
    assert not (await chat.health(changed)).cached and len(server.requests) == 3


async def test_a_health_check_needs_a_json_object(server: FakeLlmServer) -> None:
    server.scenario = respond(http_response(200, b"merhaba", content_type="text/plain"))
    probe = await adapter().health(connection(server))
    assert probe.outcome is LlmOutcome.INVALID_RESPONSE
    assert probe.message == (
        "Model sunucusuna ulaşılamadı: yanıt JSON değil — adres OpenAI uyumlu API'nin /v1 adresi mi?"
    )


# --- Requirement 14: model lists ----------------------------------------------------------------


async def test_models_carry_the_lm_studio_details(server: FakeLlmServer) -> None:
    async def scenario(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        if request.path == "/api/v0/models":
            payload = {
                "data": [
                    {
                        "id": "gemma",
                        "type": "llm",
                        "state": "loaded",
                        "max_context_length": 131072,
                        "publisher": "google",
                        "quantization": "Q4_K_M",
                    }
                ]
            }
        else:
            payload = {
                "data": [
                    {"id": "gemma", "owned_by": ""},
                    {"id": "qwen", "owned_by": "vllm", "max_model_len": 32768},
                    {"id": "phi", "context_window": 4096.0},
                ]
            }
        writer.write(json_response(payload))
        await writer.drain()

    server.scenario = scenario
    listing = await adapter().list_models(connection(server))
    assert listing.probe.ok
    rows = {model.id: model for model in listing.models}
    assert (rows["gemma"].type, rows["gemma"].loaded, rows["gemma"].context) == (
        "llm",
        True,
        131072,
    )
    assert (rows["gemma"].owner, rows["gemma"].quant) == ("google", "Q4_K_M")
    assert (rows["qwen"].loaded, rows["qwen"].context, rows["qwen"].owner) == (None, 32768, "vllm")
    assert rows["phi"].context == 4096
    assert [request.path for request in server.requests] == ["/api/v0/models", "/v1/models"]


async def test_a_failing_detail_list_is_ignored(server: FakeLlmServer) -> None:
    async def scenario(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        if request.path == "/api/v0/models":
            await asyncio.sleep(1)
            return
        writer.write(models_reply("a", "b"))
        await writer.drain()

    server.scenario = scenario
    listing = await adapter(timeouts=LlmTimeouts(lm_studio=0.2)).list_models(connection(server))
    assert listing.probe.ok and [model.loaded for model in listing.models] == [None, None]


async def test_a_hanging_server_ends_the_model_list_within_its_budget(
    server: FakeLlmServer,
) -> None:
    server.scenario = hang()
    started = time.monotonic()
    listing = await adapter().list_models(connection(server))
    assert listing.probe.outcome is LlmOutcome.TIMEOUT
    assert time.monotonic() - started < FAST.model_list_budget + 0.3


async def test_the_inventory_asks_at_most_eight_servers_at_once(server: FakeLlmServer) -> None:
    async def slow(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        await asyncio.sleep(0.15)
        writer.write(models_reply("m"))
        await writer.drain()

    server.scenario = slow
    targets = [connection(server, endpoint=server.url("/openai")) for _ in range(12)]
    timeouts = LlmTimeouts(inventory=2, inventory_server_budget=3, inventory_budget=5)
    listings = await adapter(timeouts=timeouts).list_models_of(targets)
    assert all(listing.probe.ok for listing in listings) and len(listings) == 12
    assert server.peak == 8


async def test_the_inventory_ends_within_its_total_budget(server: FakeLlmServer) -> None:
    server.scenario = hang()
    targets = [connection(server, endpoint=server.url("/openai")) for _ in range(20)]
    started = time.monotonic()
    listings = await adapter().list_models_of(targets)
    assert time.monotonic() - started < FAST.inventory_budget + 0.4
    assert {listing.probe.outcome for listing in listings} == {LlmOutcome.TIMEOUT}
    assert server.peak <= 8


async def test_a_test_chat_step_ends_within_its_ceiling_including_the_wait(
    server: FakeLlmServer,
) -> None:
    started_event = asyncio.Event()
    server.scenario = hang(started_event)
    chat = adapter(limit=1)
    holder_token = CancelToken()
    holder = asyncio.create_task(
        chat.chat(connection(server, timeout_seconds=60), ask(), cancel=holder_token)
    )
    await asyncio.wait_for(started_event.wait(), 5)
    started = time.monotonic()
    tested = await chat.chat(
        connection(server, timeout_seconds=900), ask(LlmPurpose.CONNECTION_TEST)
    )
    assert tested.outcome is LlmOutcome.TIMEOUT and tested.summary.requests == 0
    assert time.monotonic() - started < FAST.test_chat_budget + 0.3
    holder_token.cancel()
    await holder


# --- Requirement 18 and 22, Gözlemlenebilirlik --------------------------------------------------


async def test_calls_and_checks_emit_the_prd_signals_without_content(
    server: FakeLlmServer, telemetry_capture: TelemetryCapture, logs: LogCapture
) -> None:
    key = f"anahtar-{MARKER}"

    async def scenario(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        if request.method == "GET":
            writer.write(models_reply("m"))
        elif len(server.requests) == 1:
            writer.write(refusal(f"seed unsupported {MARKER}"))
        elif len(server.requests) == 2:
            writer.write(chat_reply(f"düz metin {MARKER}", prompt_tokens=5, completion_tokens=3))
        else:
            writer.write(chat_reply('{"ok": true}', prompt_tokens=7, completion_tokens=2))
        await writer.drain()

    server.scenario = scenario
    chat = adapter()
    target = connection(server, api_key=key)
    request = LlmChatRequest(
        system=f"sistem {MARKER}",
        user=f"soru {MARKER}",
        schema={"type": "object", "description": MARKER},
        max_tokens=100,
        purpose=LlmPurpose.ANALYSIS,
        analysis_public_id="analiz-1",
    )
    result = await chat.chat(target, request)
    await chat.health(target)
    await chat.health(target)

    assert result.ok and result.summary.repaired
    assert result.summary.adaptations == (AdaptedFeature.SEED,)
    capture = telemetry_capture
    assert {
        "dwhnavigator_llm_calls_total",
        "dwhnavigator_llm_call_duration_seconds",
        "dwhnavigator_llm_inflight_calls",
        "dwhnavigator_llm_waiting_calls",
        "dwhnavigator_llm_tokens_total",
        "dwhnavigator_llm_adaptations_total",
        "dwhnavigator_llm_probes_total",
    } <= capture.metric_names()
    assert capture.value("dwhnavigator_llm_calls_total", purpose="analysis", outcome="ok") == 1
    assert capture.value("dwhnavigator_llm_tokens_total", kind="prompt") == 12
    assert capture.value("dwhnavigator_llm_tokens_total", kind="completion") == 5
    assert capture.value("dwhnavigator_llm_adaptations_total", feature="seed") == 1
    assert capture.value("dwhnavigator_llm_probes_total", operation="health", outcome="ok") == 2
    assert capture.value("dwhnavigator_llm_inflight_calls") == 0
    assert capture.value("dwhnavigator_llm_waiting_calls") == 0
    for name in ("dwhnavigator_llm_calls_total", "dwhnavigator_llm_call_duration_seconds"):
        assert {tuple(sorted(labels)) for labels, _ in capture.points(name)} == {
            ("outcome", "purpose")
        }
    (span,) = capture.spans("llm chat")
    assert dict(span.attributes or {}) == {
        "dwhnavigator.llm.purpose": "analysis",
        "dwhnavigator.llm.outcome": "ok",
        "http.response.status_code": 200,
        "dwhnavigator.llm.requests": 3,
        "dwhnavigator.llm.adaptations": 1,
        "dwhnavigator.llm.repaired": True,
    }
    probes = capture.spans("llm probe")
    assert [dict(p.attributes or {}) for p in probes] == [
        {
            "dwhnavigator.llm.operation": "health",
            "dwhnavigator.llm.outcome": "ok",
            "dwhnavigator.llm.cached": cached,
        }
        for cached in (False, True)
    ]
    (call,) = logs.events("llm.call")
    assert call["analysis_public_id"] == "analiz-1" and call["adaptations"] == "seed"
    assert call["integration_public_id"] == target.public_id and call["requests"] == 3
    assert [event["cached"] for event in logs.events("llm.probe")] == [False, True]
    everything = "\n".join(
        [capture.everything(), logs.rendered(), json.dumps(result.summary.as_dict())]
    )
    for secret in (MARKER, key, "127.0.0.1"):
        assert secret not in everything
    assert "deneme-model" not in capture.everything()


async def test_unknown_labels_become_other(telemetry_capture: TelemetryCapture) -> None:
    from app.core import telemetry

    telemetry.record_llm_call(
        purpose="gizli", outcome="yeni", duration_seconds=1, prompt_tokens=0, completion_tokens=0
    )
    telemetry.record_llm_probe(operation="x", outcome="y")
    telemetry.record_llm_adaptation("z")
    assert (
        telemetry_capture.value("dwhnavigator_llm_calls_total", purpose="other", outcome="other")
        == 1
    )
    assert (
        telemetry_capture.value("dwhnavigator_llm_probes_total", operation="other", outcome="other")
        == 1
    )
    assert telemetry_capture.value("dwhnavigator_llm_adaptations_total", feature="other") == 1


async def test_a_failed_call_logs_only_its_class(
    server: FakeLlmServer, logs: LogCapture, telemetry_capture: TelemetryCapture
) -> None:
    server.scenario = respond(json_response({"error": f"iç hata {MARKER}"}, 500))
    result = await adapter().chat(connection(server), ask(user=f"soru {MARKER}"))
    assert result.outcome is LlmOutcome.UPSTREAM_STATUS
    (event,) = logs.events("llm.call")
    assert event["outcome"] == "upstream_status" and event["http_status"] == 500
    assert MARKER not in logs.rendered() and MARKER not in telemetry_capture.everything()
    (span,) = telemetry_capture.spans("llm chat")
    assert span.status.status_code.name == "ERROR" and not span.status.description
