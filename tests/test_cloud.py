"""Hosted models for the model lab (ADR-026): retries, feature adaptation, settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from vsa.config import CloudSettings, cloud_api_key, load_settings
from vsa.llm.client import LLMError, OpenAICompatibleClient, retry_delay
from vsa.web.settings_schema import is_chat_model, values_of

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


def test_retry_delay_sources() -> None:
    assert retry_delay("7", "", 0) == 8
    assert retry_delay(None, '{"retryDelay": "31s"}', 0) == 32
    assert retry_delay(None, "", 2) == 20  # 5 * 2^2
    assert retry_delay(None, "", 9) == 90  # capped


class FakeServer:
    """Stands in for ``_post``: refuses features like Gemma on a hosted API does."""

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


def test_cloud_key_from_settings_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert cloud_api_key(CloudSettings()) == ""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-env")
    assert cloud_api_key(CloudSettings()) == "nvapi-env"
    assert cloud_api_key(CloudSettings(api_key="nvapi-file")) == "nvapi-file"


def test_cloud_secret_never_leaves_and_blank_keeps(tmp_path: Path) -> None:
    f = tmp_path / "s.yaml"
    f.write_text("cloud:\n  enabled: true\n  api_key: nvapi-secret\n", encoding="utf-8")
    values = values_of(load_settings(f))
    assert values["cloud.api_key"] == "" and values["cloud.enabled"] is True


def test_chat_model_filter() -> None:
    assert is_chat_model("meta/llama-3.3-70b-instruct")
    assert is_chat_model("google/gemma-3-27b-it")
    assert not is_chat_model("nvidia/nv-embedqa-e5-v5")
    assert not is_chat_model("nvidia/llama-3.1-nemoguard-8b-content-safety")
    assert not is_chat_model("qwen/qwen2.5-vl-72b-instruct")


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


def test_cloud_provider_splits_chat_and_embeddings() -> None:
    from vsa.config import LLMSettings
    from vsa.llm.client import SplitClient, client_from_settings

    llm = LLMSettings(enabled=True, endpoint="http://127.0.0.1:1234/v1",
                      model="google/gemma-4-31b-it", embedding_model="bge", provider="cloud",
                      seed=7)  # fmt: skip
    cloud = CloudSettings(enabled=True, api_key="nvapi-x")
    c = client_from_settings(llm, embeddings=True, cloud=cloud)
    assert isinstance(c, SplitClient) and c.available and c.model == "google/gemma-4-31b-it"
    assert isinstance(c.chat, OpenAICompatibleClient) and c.chat.endpoint == cloud.endpoint
    assert c.chat.seed == 7 and c.chat.api_key == "nvapi-x"
    assert isinstance(c.embedder, OpenAICompatibleClient)
    assert c.embedder.endpoint == "http://127.0.0.1:1234/v1" and c.embedder.embedding_model == "bge"
    no_key = client_from_settings(llm, embeddings=True, cloud=CloudSettings(enabled=True))
    assert not no_key.available  # cloud chosen without a key: judge off, rules still work
