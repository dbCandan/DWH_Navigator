"""The record's form of the answer outlives the dictionary (question-analysis Requirement 7, 16,
18, Decision 10) and the result envelope keeps the source's fields."""

from __future__ import annotations

import pytest

from app.domain.analysis import Dictionary
from app.services.analysis import answer_cache, serialize
from app.services.analysis.answer_record import from_record_form, record_form
from app.services.analysis.config import Settings
from app.services.analysis.pipeline import Engine, Resources
from tests.parity.fake_model import FakeAnalyst
from tests.parity.run_target import TargetClient

pytestmark = pytest.mark.unit


def test_the_answer_comes_back_without_the_dictionary(sample_dictionary: Dictionary) -> None:
    core = FakeAnalyst()
    query = "kart limit doluluk oranı"
    core.begin(query, "normal")
    engine = Engine(sample_dictionary, Settings(), Resources(), llm=TargetClient(core))
    result = engine.analyze(query, 5)
    assert result.analyst and result.objects
    stored = record_form(result)
    assert isinstance(stored["objects"][0]["columns"][0]["col"], dict)
    again = from_record_form(stored)
    assert again is not None
    assert answer_cache.encode(again) == answer_cache.encode(result)
    assert serialize.analysis(again) == serialize.analysis(result)
    assert from_record_form({"objects": "bozuk"}) is None


def test_a_row_field_the_column_no_longer_has_is_ignored(sample_dictionary: Dictionary) -> None:
    core = FakeAnalyst()
    query = "kart limit doluluk oranı"
    core.begin(query, "normal")
    engine = Engine(sample_dictionary, Settings(), Resources(), llm=TargetClient(core))
    result = engine.analyze(query, 5)
    stored = record_form(result)
    for match in stored["objects"]:
        for hit in match["columns"]:
            hit["col"]["has_pii"] = True
    again = from_record_form(stored)
    assert again is not None
    assert serialize.analysis(again) == serialize.analysis(result)


def test_the_envelope_has_the_sources_fields(sample_dictionary: Dictionary) -> None:
    core = FakeAnalyst()
    core.begin("kart", "normal")
    engine = Engine(sample_dictionary, Settings(), Resources(), llm=TargetClient(core))
    data = serialize.analysis(engine.analyze("kart", 5))
    assert list(data) == [
        "query", "verdict", "summary", "objects", "near", "notes", "concepts", "expansion",
        "method", "elapsed_ms", "dictionary_version", "llm_model", "analyst", "fallback",
        "interpretation", "design", "attention", "reused", "missing",
    ]  # fmt: skip
    assert data["reused"] is None
