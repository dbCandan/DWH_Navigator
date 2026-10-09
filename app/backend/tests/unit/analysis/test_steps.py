"""The record's steps, phases and model use (analysis-records Requirement 3, Decision 9) and the
trace's keyed steps that feed the live stream (question-analysis Requirement 10 and 18)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.analysis import trace
from app.services.analysis.steps import MAX_STEPS, PHASE_NAMES, record_steps, step_of

pytestmark = pytest.mark.unit


def _span(**over: Any) -> dict[str, Any]:
    base = {"id": 0, "parent": None, "name": "x", "kind": "step", "start_ms": 0, "ms": 0,
            "status": "ok"}  # fmt: skip
    return base | over


def _call(prompt: int, completion: int) -> dict[str, Any]:
    return {"prompt_tokens": prompt, "completion_tokens": completion, "outcome": "ok"}


def test_phases_come_from_the_keys_of_step_kind_only() -> None:
    spans = [
        _span(id=0, key="queue", ms=1500),
        _span(id=1, key="saved_answer_lookup", ms=10),
        _span(id=2, key="saved_answer_lookup", ms=5),
        _span(id=3, key="model_check", ms=20),
        _span(id=4, name="Analist akışı", ms=9000),
        _span(id=5, parent=4, key="rule_hints", ms=300),
        _span(id=6, parent=5, name="BM25 arama", ms=100),
        _span(id=7, parent=4, key="shortlist", ms=4000),
        _span(id=8, parent=7, kind="llm", ms=3900, data={"call": _call(70000, 900)}),
        _span(id=9, parent=4, key="family_search", ms=50),
        _span(id=10, parent=4, key="analyst_report", ms=4600),
        _span(id=11, parent=10, kind="llm", ms=4500, data={"call": _call(30000, 2500)}),
        _span(id=12, parent=10, kind="event", key="analyst_report", ms=999),
    ]
    recorded = record_steps(spans)
    assert recorded.phases == {
        "queue": 1500,
        "saved_answer_lookup": 15,
        "model_check": 20,
        "rule_hints": 300,
        "analyst_pick": 4050,
        "analyst_write": 4600,
    }
    assert list(recorded.phases) == list(PHASE_NAMES)
    assert (recorded.llm_calls, recorded.prompt_tokens, recorded.completion_tokens) == (
        2, 100000, 3400
    )  # fmt: skip
    assert recorded.steps[8]["call"]["prompt_tokens"] == 70000
    assert recorded.steps[6]["key"] is None and not recorded.truncated


def test_limits_and_unknown_values() -> None:
    step = step_of(_span(name="ad" * 100, detail="ayrıntı" * 100, key="bilinmiyor",
                         kind="tuhaf", status="tuhaf"))  # fmt: skip
    assert len(step["name"]) == 120 and len(step["detail"]) == 300
    assert (step["key"], step["kind"], step["status"]) == (None, "event", "error")
    many = record_steps([_span(id=n) for n in range(MAX_STEPS + 3)])
    assert len(many.steps) == MAX_STEPS and many.truncated


def test_a_step_left_open_is_an_error_at_the_end() -> None:
    with trace.recording() as tr:
        s = tr.open("Analist akışı", None, trace.STEP)
        s.key = "rule_hints"
    recorded = record_steps(tr.to_list())
    assert recorded.steps[0]["status"] == "error" and recorded.steps[0]["key"] == "rule_hints"


def test_keyed_steps_are_heard_when_they_start_and_end() -> None:
    heard: list[tuple[str, str]] = []
    tr = trace.Trace(listener=lambda span, what: heard.append((span.key, what)))
    with trace.recording(tr):
        with trace.span("Kural motoru ipuçları", key="rule_hints"), trace.span("BM25 arama"):
            pass
        with pytest.raises(RuntimeError), trace.span("2. adım", key="analyst_report"):
            raise RuntimeError
    assert heard == [
        ("rule_hints", "started"),
        ("rule_hints", "finished"),
        ("analyst_report", "started"),
        ("analyst_report", "error"),
    ]
    assert [s.get("key") for s in tr.to_list()] == ["rule_hints", None, "analyst_report"]
