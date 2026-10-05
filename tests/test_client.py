"""OpenAI-compatible client: retries, feature adaptation, seed, health."""

from __future__ import annotations

from typing import Any

import pytest

from vsa.config import LLMSettings
from vsa.llm.client import (
    NO_MODEL,
    LLMError,
    NullClient,
    OpenAICompatibleClient,
    client_from_settings,
    retry_delay,
)

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


def test_retry_delay_sources() -> None:
    assert retry_delay("7", "", 0) == 8
    assert retry_delay(None, '{"retryDelay": "31s"}', 0) == 32
    assert retry_delay(None, "", 2) == 20  # 5 * 2^2
    assert retry_delay(None, "", 9) == 90  # capped


class FakeServer:
    """Stands in for ``_post``: refuses features the way some model servers do."""

    def __init__(self, refuse: set[str]) -> None:
        self.refuse = refuse
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.bodies.append(body)
        if "system" in self.refuse and any(m["role"] == "system" for m in body["messages"]):
            raise LLMError(f"{path}: HTTP 400: Developer instruction is not enabled for model")
        if "json" in self.refuse and "response_format" in body:
            raise LLMError(f"{path}: HTTP 400: JSON mode is not enabled for model")
        if "reasoning" in self.refuse and "reasoning_effort" in body:
            raise LLMError(f"{path}: HTTP 400: reasoning_effort is not supported")
        return {"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 7}}


def _client(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> OpenAICompatibleClient:
    c = OpenAICompatibleClient("https://example.test/v1", "m", reasoning_effort="none")
    monkeypatch.setattr(c, "_post", server)
    return c


def test_client_drops_refused_features_and_remembers(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer({"system", "json", "reasoning"})
    c = _client(server, monkeypatch)
    assert c.chat_json("SİSTEM", "soru", SCHEMA) == {"ok": True}
    assert (c.system_role, c.structured, c.reasoning_effort) == (False, False, "")
    first = server.bodies[-1]["messages"][0]
    assert first["role"] == "user" and first["content"].startswith("SİSTEM")
    n = len(server.bodies)
    assert c.chat_json("SİSTEM", "soru 2", SCHEMA) == {"ok": True}
    assert len(server.bodies) == n + 1  # learned: no second round of refusals


def test_client_keeps_features_the_model_accepts(monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(set())
    c = _client(server, monkeypatch)
    assert c.chat_json("s", "u", SCHEMA) == {"ok": True}
    body = server.bodies[0]
    assert "response_format" in body and body["messages"][0]["role"] == "system"
    assert len(server.bodies) == 1
    assert (c.calls, c.prompt_tokens, c.completion_tokens) == (1, 100, 7)  # usage counter


def test_client_gives_up_on_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        raise LLMError(f"{path}: HTTP 401: invalid api key")

    c = OpenAICompatibleClient("https://example.test/v1", "m")
    monkeypatch.setattr(c, "_post", fail)
    assert c.chat_json("s", "u", SCHEMA) is None and c.failures == 1


def test_seed_is_sent_and_dropped_if_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies: list[dict[str, Any]] = []

    def server(path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        bodies.append(body)
        if "seed" in body and len(bodies) == 1:
            raise LLMError(f"{path}: HTTP 400: unsupported parameter: seed")
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    c = OpenAICompatibleClient("https://example.test/v1", "m", seed=42)
    monkeypatch.setattr(c, "_post", server)
    assert c.chat_json("s", "u", SCHEMA) == {"ok": True}
    assert bodies[0]["seed"] == 42 and "seed" not in bodies[1] and c.seed is None
    assert OpenAICompatibleClient("https://example.test/v1", "m", seed=-1).seed is None


def test_health_is_cached_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def down(url: str, timeout: float) -> dict[str, Any]:
        calls.append(url)
        raise LLMError("Model sunucusuna ulaşılamadı (http://spark:8000/v1): bağlantı reddedildi")

    monkeypatch.setattr("vsa.llm.client._HEALTH", {})
    c = OpenAICompatibleClient("http://spark:8000/v1", "m")
    monkeypatch.setattr(c, "_get", down)
    assert "reddedildi" in c.health()
    assert "reddedildi" in c.health() and len(calls) == 1  # reused, not asked again
    assert OpenAICompatibleClient("http://spark:8000/v1", "").health()  # no chat model
    assert NullClient().health() == NO_MODEL


def test_unreachable_server_fails_fast() -> None:
    """Connecting gives up quickly even with a long answer timeout (ADR-034)."""
    import time

    c = OpenAICompatibleClient("http://127.0.0.1:9/v1", "m", timeout=900)
    t0 = time.perf_counter()
    reason = c.health()
    assert reason and "reddedildi" in reason
    assert time.perf_counter() - t0 < 15


def test_client_from_settings_carries_the_connection() -> None:
    llm = LLMSettings(enabled=True, endpoint="http://127.0.0.1:1234/v1", model="chat", seed=7)
    c = client_from_settings(llm)
    assert isinstance(c, OpenAICompatibleClient) and c.available and c.model == "chat"
    assert c.seed == 7
