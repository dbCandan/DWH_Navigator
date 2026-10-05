"""ADR-035: earlier analyst answers given again — keys, fingerprint, store, web flow."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from vsa import answer_cache
from vsa.config import Settings
from vsa.loader import load_dictionary
from vsa.models import AnalysisResult, TermGroup
from vsa.pipeline import Engine, Resources
from vsa.web.answer_store import AnswerStore
from vsa.web.server import App

GROUPS = [TermGroup("müşteri no", ("hesap no", "customer id"))]


@pytest.fixture
def engine(sample_dictionary_path: Path) -> Engine:
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    d = load_dictionary(sample_dictionary_path, "Kolonlar", "Kalite")
    return Engine(d, s, Resources(GROUPS, frozenset({"ve", "ile", "bir"})))


def test_text_key_ignores_case_letters_and_punctuation() -> None:
    assert answer_cache.text_key("Kart  LİMİT doluluk oranı?") == answer_cache.text_key(
        "kart limit, doluluk orani"
    )
    assert answer_cache.text_key("kart limiti") != answer_cache.text_key("kart limit")


def test_meaning_key_joins_term_group_members(engine: Engine) -> None:
    _, a = engine.cache_keys("Müşteri no ile kart limit doluluk oranı")
    _, b = engine.cache_keys("kart limit doluluk oranı ve hesap no")
    _, c = engine.cache_keys("kart limit doluluk oranı")
    assert a and a == b
    assert a != c


def test_meaning_key_keeps_numbers_and_negations(engine: Engine) -> None:
    keys = {engine.cache_keys(q)[1] for q in (
        "son 3 ay kart limit doluluk", "son 6 ay kart limit doluluk",
        "kart limiti olmayan müşteri", "kart limiti müşteri",
    )}  # fmt: skip
    assert len(keys) == 4


def test_meaning_key_empty_without_content(engine: Engine) -> None:
    assert engine.cache_keys("ve ile")[1] == ""


def test_fingerprint_follows_what_shapes_an_answer(engine: Engine) -> None:
    fp = engine.cache_fingerprint(5)
    assert fp == engine.cache_fingerprint(5)
    assert fp != engine.cache_fingerprint(3)
    engine.settings.report.out_dir = "elsewhere"  # does not change an answer
    assert fp == engine.cache_fingerprint(5)
    engine.settings.llm.model = "another-model"
    assert fp != engine.cache_fingerprint(5)
    other = answer_cache.fingerprint(engine.settings, "other-version", "", GROUPS, 5)
    assert other != engine.cache_fingerprint(5)


def test_encode_decode_round_trip(engine: Engine) -> None:
    r = engine.analyze("kart limit doluluk oranı")
    assert r.objects
    back = answer_cache.decode(answer_cache.encode(r), engine.dictionary.by_key())
    assert back == r
    assert answer_cache.decode(answer_cache.encode(r), {}) is None  # columns gone


def test_store_lookup_replace_forget(tmp_path: Path) -> None:
    path = tmp_path / "answers.jsonl"
    store = AnswerStore(path)
    store.put("Soru A", "soru a", "m1", "fp", {"n": 1})
    store.put("soru a!", "soru a", "m1", "fp", {"n": 2})  # same words: replaces
    store.put("Soru B", "soru b", "m1", "fp", {"n": 3})
    hit = store.lookup("soru a", "m1", "fp", use_meaning=True, max_age_days=30)
    assert hit and hit.match == "aynı soru" and hit.entry["result"] == {"n": 2}
    hit = store.lookup("soru c", "m1", "fp", use_meaning=True, max_age_days=30)
    assert hit and hit.match == "aynı anlam" and hit.entry["result"] == {"n": 3}  # newest
    assert store.lookup("soru c", "m1", "fp", use_meaning=False, max_age_days=30) is None
    assert store.lookup("soru a", "m1", "other", use_meaning=True, max_age_days=30) is None
    assert AnswerStore(path).stats("fp")["total"] == 2  # survives a restart
    assert store.forget("soru x", "m1") == 2
    assert store.clear() == 0 and not path.exists()


@pytest.fixture
def app(engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    """An app whose engine "has a model": every answer comes back as the analyst's."""
    calls: list[str] = []
    rules = engine.analyze

    def analyst(query: str, top_n: int = 5) -> AnalysisResult:
        calls.append(query)
        return replace(rules(query, top_n), analyst=True, llm_model="test-model")

    monkeypatch.setattr(engine, "analyze", analyst)
    a = App(engine, tmp_path / "out", tmp_path / "feedback.jsonl")
    a.calls = calls  # type: ignore[attr-defined]
    return a


def test_web_reuses_answer_for_same_and_equivalent_question(app: App) -> None:
    calls: list[str] = app.calls  # type: ignore[attr-defined]
    first = app.ask({"query": "kart limit doluluk oranı müşteri no"})
    assert first["reused"] is None and len(calls) == 1
    again = app.ask({"query": "Kart limit doluluk oranı, müşteri no"})
    assert again["reused"]["match"] == "aynı soru" and len(calls) == 1
    assert again["objects"] == first["objects"]
    same = app.ask({"query": "hesap no kart limit doluluk oranı"})
    assert same["reused"]["match"] == "aynı anlam" and len(calls) == 1
    assert same["query"] == "hesap no kart limit doluluk oranı"
    fresh = app.ask({"query": "kart limit doluluk oranı müşteri no", "fresh": True})
    assert fresh["reused"] is None and len(calls) == 2
    flows = [e["flow"] for e in app.analyses()["items"]]
    assert flows == ["analist", "önbellek", "önbellek", "analist"][::-1]


def test_web_does_not_keep_rule_answers(engine: Engine, tmp_path: Path) -> None:
    app = App(engine, tmp_path / "out", tmp_path / "feedback.jsonl")
    app.ask({"query": "kart limit doluluk oranı"})
    assert app.ask({"query": "kart limit doluluk oranı"})["reused"] is None


def test_web_cache_switch_and_clear(app: App) -> None:
    calls: list[str] = app.calls  # type: ignore[attr-defined]
    app.ask({"query": "kart limit doluluk oranı"})
    app.engine.settings.cache.enabled = False
    assert app.ask({"query": "kart limit doluluk oranı"})["reused"] is None
    app.engine.settings.cache.enabled = True
    assert app.clear_answers() == {"removed": 1}
    assert app.ask({"query": "kart limit doluluk oranı"})["reused"] is None
    assert len(calls) == 3
