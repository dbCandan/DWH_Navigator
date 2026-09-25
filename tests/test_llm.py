"""M3/M4: LLM client parsing, judge, dense index — with a fake model, no server needed."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vsa.config import Settings
from vsa.index.dense import DenseIndex, build_dense_index, column_text, load_dense_index
from vsa.llm.client import LLMError, NullClient, client_from_settings, parse_json_reply
from vsa.llm.judge import candidate_payload, judge
from vsa.models import ColumnHit, DictColumn, Level, ObjectMatch
from vsa.pipeline import Engine


class FakeClient:
    """Deterministic stand-in: bag-of-letters embeddings, scripted chat replies."""

    available = True
    model = "fake-llm"

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


class TestJudge:
    def test_payload_ids_and_truncation(self) -> None:
        long = "uzun " * 200
        payload, ids = candidate_payload([match("DB.S.vA", col(0, "vA", "X", long))])
        assert ids == {"t1": "DB.S.vA"}
        rows = json.loads(payload)
        assert rows[0]["alanlar"][0]["aciklama"].endswith("…")
        assert len(rows[0]["alanlar"][0]["aciklama"]) < 240

    def test_unknown_ids_dropped_and_counted(self) -> None:
        reply = {
            "matches": [
                {
                    "candidate_id": "t1",
                    "confidence": 1.7,
                    "reason": "r",
                    "caveat": "",
                    "usage": "u",
                },
                {
                    "candidate_id": "t9",
                    "confidence": 0.9,
                    "reason": "x",
                    "caveat": "-",
                    "usage": "-",
                },
            ]
        }
        result = judge("q", [match("DB.S.vA", col(0, "vA", "X", "d"))], FakeClient(reply))
        assert result is not None
        assert list(result.verdicts) == ["DB.S.vA"]
        assert result.verdicts["DB.S.vA"].confidence == 1.0  # clipped
        assert result.verdicts["DB.S.vA"].caveat == "-"
        assert result.unknown_ids == 1

    def test_failure_returns_none(self) -> None:
        assert judge("q", [match("DB.S.vA", col(0, "vA", "X", "d"))], FakeClient(None)) is None


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
        loaded = load_dense_index(tmp_path, 2)
        assert loaded is not None and loaded.model == "fake-emb"
        assert load_dense_index(tmp_path, 3) is None  # dictionary changed

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


def test_judge_rescoring(sample_dictionary_path: Path) -> None:
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    s.llm.enabled = True
    base = Engine.from_dictionary_file(s)
    reply = {"matches": [{"candidate_id": "t1", "confidence": 0.9, "reason": "LLM gerekçe",
                          "caveat": "LLM kısıt", "usage": "LLM kullanım"}]}  # fmt: skip
    engine = Engine(base.dictionary, s, base.resources, llm=FakeClient(reply))
    result = engine.analyze("kart limit doluluk oranı")
    top = result.objects[0]
    assert top.llm_confidence == 0.9 and top.rule_score is not None
    assert abs(top.score - (0.6 * top.rule_score + 0.4 * 0.9)) < 1e-9
    assert top.reason == "LLM gerekçe" and top.caveat.startswith("LLM kısıt")
    assert result.llm_model == "fake-llm"
    assert any("LLM hakem" in m for m in result.method)


def test_llm_expansion_only_widens_bm25(sample_dictionary_path: Path) -> None:
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    s.llm.enabled, s.llm.expand_query, s.llm.judge = True, True, False
    base = Engine.from_dictionary_file(s)
    reply = {
        "synonyms_tr": ["kullanım oranı"],
        "terms_en": ["utilization"],
        "column_name_guesses": [],
    }
    engine = Engine(base.dictionary, s, base.resources, llm=FakeClient(reply))
    _, q = engine.rank_objects("kart doluluk")
    assert q.sparse_terms.get("utilization") == s.expansion.weight
    assert "utilization" not in {c.label for c in q.concepts}
