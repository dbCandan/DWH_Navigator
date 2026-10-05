"""LLM client parsing and the dense index — with a fake model, no server needed."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vsa.config import Settings
from vsa.index.dense import (
    DenseIndex,
    build_dense_index,
    build_object_index,
    column_staleness,
    column_text,
    load_dense_index,
    load_object_index,
)
from vsa.llm.client import LLMError, NullClient, client_from_settings, parse_json_reply
from vsa.models import ColumnHit, DictColumn, Level, ObjectMatch
from vsa.pipeline import Engine


class FakeClient:
    """Deterministic stand-in: bag-of-letters embeddings, scripted chat replies."""

    available = True
    model = "fake-llm"
    down = ""  # health(): "" = the server answers

    def health(self) -> str:
        return self.down

    def __init__(self, reply: dict[str, Any] | None = None, fail_embed: bool = False) -> None:
        self.reply = reply
        self.fail_embed = fail_embed
        self.embedded = 0
        self.prompts: list[str] = []

    def chat_json(
        self, system: str, user: str, schema: Mapping[str, Any], *, max_tokens: int = 1024
    ) -> dict[str, Any] | None:
        self.prompts.append(user)
        return self.reply

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail_embed:
            raise LLMError("down")
        self.embedded += len(texts)
        out = []
        for t in texts:
            v = [0.0] * 26
            for ch in t.lower():
                if "a" <= ch <= "z":
                    v[ord(ch) - 97] += 1
            out.append(v)
        return out


def col(i: int, obj: str, name: str, desc: str) -> DictColumn:
    return DictColumn(i, "DB", "S", obj, name, desc, desc)


def match(key: str, *cols: DictColumn, score: float = 0.8) -> ObjectMatch:
    return ObjectMatch(
        key, "DB", "S", key.rsplit(".", 1)[-1], [], score, Level.HIGH,
        [ColumnHit(c, 1.0, score) for c in cols], {}, [], [],
    )  # fmt: skip


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
    with pytest.raises(LLMError):
        NullClient().embed(["x"])
    s = Settings()
    assert isinstance(client_from_settings(s.llm), NullClient)
    s.llm.enabled, s.llm.endpoint, s.llm.model = True, "http://localhost:1/v1", "m"
    assert client_from_settings(s.llm).available
    # Chat off but dense on: embeddings still available, the analyst not.
    s.llm.enabled, s.llm.embedding_model = False, "emb"
    embed_only = client_from_settings(s.llm, embeddings=True)
    assert not embed_only.available and not isinstance(embed_only, NullClient)
    assert isinstance(client_from_settings(s.llm, embeddings=False), NullClient)


class TestDense:
    def test_build_resume_and_load(self, tmp_path: Path) -> None:
        cols = [col(i, "vA", n, d) for i, (n, d) in enumerate([("Alpha", "aaa"), ("Beta", "bbb")])]
        client = FakeClient()
        idx = build_dense_index(cols, client, "fake-emb", tmp_path, batch_size=1)
        assert idx.vectors.shape == (2, 26)
        assert client.embedded == 2
        again = FakeClient()
        build_dense_index(cols, again, "fake-emb", tmp_path)
        assert again.embedded == 0  # everything cached
        loaded = load_dense_index(tmp_path, cols)
        assert loaded is not None and loaded.model == "fake-emb"
        extra = [*cols, col(2, "vA", "Gamma", "ccc")]
        assert load_dense_index(tmp_path, extra) is None  # dictionary changed

    def test_rows_follow_columns_not_file_order(self, tmp_path: Path) -> None:
        """A reordered dictionary keeps each column's own vector; a changed description
        or an index saved without text hashes is stale, never silently misaligned."""
        cols = [col(i, "vA", n, d) for i, (n, d) in enumerate([("Alpha", "aaa"), ("Beta", "bbb")])]
        built = build_dense_index(cols, FakeClient(), "fake-emb", tmp_path)
        swapped = [col(0, "vA", "Beta", "bbb"), col(1, "vA", "Alpha", "aaa")]
        loaded = load_dense_index(tmp_path, swapped)
        assert loaded is not None
        assert np.allclose(loaded.vectors[0], built.vectors[1])
        assert np.allclose(loaded.vectors[1], built.vectors[0])

        edited = [col(0, "vA", "Alpha", "aaa düzeltildi"), cols[1]]
        assert load_dense_index(tmp_path, edited) is None
        meta_path = tmp_path / "dense_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert column_staleness(meta, edited) == 1 and column_staleness(meta, cols) == 0
        del meta["keys"]  # index built before hashes were stored
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        assert load_dense_index(tmp_path, cols) is None
        assert column_staleness(meta, cols) == 2

    def test_object_vectors_checked_by_text(self, tmp_path: Path) -> None:
        a, b = col(0, "vA", "Alpha", "aaa"), col(1, "vB", "Beta", "bbb")
        objects = {"E.S.vA": [a], "E.S.vB": [b]}
        build_object_index(objects, FakeClient(), "fake-emb", tmp_path)
        assert load_object_index(tmp_path, objects) is not None
        changed = {"E.S.vA": [a, col(2, "vA", "Gamma", "ccc")], "E.S.vB": [b]}
        assert load_object_index(tmp_path, changed) is None  # same keys, new content

    def test_search_order(self) -> None:
        v = np.eye(3, dtype=np.float32)
        idx = DenseIndex(v, "m")
        assert [i for i, _ in idx.search(np.array([0, 1, 0], dtype=np.float32), 2)][0] == 1

    def test_column_text(self) -> None:
        text = column_text(
            DictColumn(0, "D", "S", "vT", "CardLimit", "Limit.", "Limit.", ("kart limiti",))
        )
        assert "Card Limit" in text and "kart limiti" in text and "vT" in text


def test_engine_degrades_when_embedding_fails(sample_dictionary_path: Path) -> None:
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    s.dense.enabled = True
    base = Engine.from_dictionary_file(s)
    dense = DenseIndex(np.ones((len(base.dictionary.columns), 26), dtype=np.float32), "fake")
    engine = Engine(
        base.dictionary, s, base.resources, llm=FakeClient(fail_embed=True), dense=dense
    )
    ranked, _ = engine.rank_objects("kart limit doluluk")
    assert ranked  # still answers, BM25 only
    assert not engine.hybrid


def test_localhost_is_pinned_to_ipv4() -> None:
    from vsa.llm.client import OpenAICompatibleClient

    c = OpenAICompatibleClient("http://localhost:1234/v1/", "m")
    assert c.endpoint == "http://127.0.0.1:1234/v1"
