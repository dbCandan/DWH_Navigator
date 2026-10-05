"""LLM client parsing and the client factory — no server needed."""

from __future__ import annotations

from vsa.config import Settings
from vsa.llm.client import (
    NullClient,
    OpenAICompatibleClient,
    client_from_settings,
    parse_json_reply,
)


class TestParse:
    def test_plain(self) -> None:
        assert parse_json_reply('{"a": 1}') == {"a": 1}

    def test_fenced_and_thinking(self) -> None:
        text = '<think>hmm</think>\n```json\n{"matches": []}\n```'
        assert parse_json_reply(text) == {"matches": []}

    def test_thought_block_with_draft_json(self) -> None:
        text = '<thought>taslak: `{"secim": 2, "gerekce": "ya`</thought>{"secim": 1}'
        assert parse_json_reply(text) == {"secim": 1}

    def test_prose_around(self) -> None:
        assert parse_json_reply('Tabii: {"x": [1]} umarım yardımcı olur') == {"x": [1]}

    def test_garbage(self) -> None:
        assert parse_json_reply("yok") is None
        assert parse_json_reply("[1, 2]") is None


def test_null_client_and_factory() -> None:
    assert NullClient().chat_json("s", "u", {}) is None
    s = Settings()
    assert isinstance(client_from_settings(s.llm), NullClient)
    s.llm.enabled, s.llm.endpoint, s.llm.model = True, "http://localhost:1/v1", "m"
    assert client_from_settings(s.llm).available
    s.llm.enabled = False  # chat off: no client at all, the rule engine answers
    assert isinstance(client_from_settings(s.llm), NullClient)


def test_localhost_is_pinned_to_ipv4() -> None:
    c = OpenAICompatibleClient("http://localhost:1234/v1/", "m")
    assert c.endpoint == "http://127.0.0.1:1234/v1"
