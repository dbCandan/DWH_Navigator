"""ADR-035: earlier analyst answers given again — keys, fingerprint and the stored form.
The saved-answer repository is tested against PostgreSQL with the job service."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.analysis import Dictionary, TermGroup
from app.services.analysis import answer_cache
from app.services.analysis.config import Settings
from app.services.analysis.llm.port import ModelSampling
from app.services.analysis.pipeline import Engine, Resources

pytestmark = pytest.mark.unit

GROUPS = [TermGroup("müşteri no", ("hesap no", "customer id"))]
MODEL = ModelSampling("test-model", 0.0, "none", 42)
Q = "kart limit doluluk oranı"


@pytest.fixture
def engine(sample_dictionary: Dictionary) -> Engine:
    return Engine(sample_dictionary, Settings(), Resources(GROUPS, frozenset({"ve", "ile", "bir"})))


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
    fp = engine.cache_fingerprint(Q, 5, MODEL)
    assert fp == engine.cache_fingerprint(Q, 5, MODEL)
    assert fp != engine.cache_fingerprint(Q, 3, MODEL)
    engine.settings.cache.max_age_days = 7  # does not change an answer
    engine.settings.cache.meaning = False
    assert fp == engine.cache_fingerprint(Q, 5, MODEL)
    assert fp != engine.cache_fingerprint(Q, 5, replace(MODEL, model="another-model"))
    assert fp != engine.cache_fingerprint(Q, 5, replace(MODEL, temperature=0.2))
    other = answer_cache.fingerprint(engine.settings, MODEL, "other-version", GROUPS, 5)
    assert other != engine.cache_fingerprint(Q, 5, MODEL)
    # the word lists count by content
    engine.resources.stopwords = engine.resources.stopwords | {"yeni"}
    assert fp != engine.cache_fingerprint(Q, 5, MODEL)
    fp = engine.cache_fingerprint(Q, 5, MODEL)
    engine.settings.analyst.shortlist = 6
    assert fp != engine.cache_fingerprint(Q, 5, MODEL)


def test_fingerprint_counts_only_the_term_groups_the_question_matches(engine: Engine) -> None:
    """A term added for another subject keeps a question's saved answer; a change in a group
    the question matches does not; the list's order does not count."""
    asked = "müşteri no ile kart limit doluluk oranı"
    fp = engine.cache_fingerprint(asked, 5, MODEL)
    unrelated = TermGroup("ikametgah", ("adres", "ev adresi"))
    engine.expander = engine_with([unrelated, *GROUPS], engine).expander
    assert engine.cache_fingerprint(asked, 5, MODEL) == fp
    engine.expander = engine_with([*GROUPS, unrelated], engine).expander
    assert engine.cache_fingerprint(asked, 5, MODEL) == fp
    changed = TermGroup("müşteri no", ("hesap no", "customer id", "CIF"))
    engine.expander = engine_with([changed, unrelated], engine).expander
    assert engine.cache_fingerprint(asked, 5, MODEL) != fp


def engine_with(groups: list[TermGroup], base: Engine) -> Engine:
    return Engine(base.dictionary, base.settings, Resources(groups, base.resources.stopwords))


def test_fingerprint_follows_the_prompt(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """An answer written under an older analyst prompt is not given again."""
    from app.services.analysis.llm import analyst_prompts

    fp = engine.cache_fingerprint(Q, 5, MODEL)
    monkeypatch.setattr(analyst_prompts, "ANALYST_RULES", analyst_prompts.ANALYST_RULES + " ")
    assert fp != engine.cache_fingerprint(Q, 5, MODEL)


def test_encode_decode_round_trip(engine: Engine) -> None:
    r = engine.rule_answer("kart limit doluluk oranı")
    assert r.objects
    back = answer_cache.decode(answer_cache.encode(r), engine.dictionary.by_key())
    assert back == r
    assert answer_cache.decode(answer_cache.encode(r), {}) is None  # columns gone
