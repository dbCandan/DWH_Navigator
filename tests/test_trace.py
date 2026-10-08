"""Request tracing (admin screen): spans nest, carry into worker threads, cost nothing
when no one records."""

from __future__ import annotations

import time

import pytest

from vsa import trace


def test_no_recording_is_a_no_op() -> None:
    with trace.span("x") as s:
        assert s is None
    trace.event("y")
    trace.count(prompt_tokens=5)
    lap = trace.Laps()
    lap("a")
    lap.note("n")
    lap.done()
    assert trace.current() is None


def test_spans_nest_and_time() -> None:
    with trace.recording() as tr, trace.span("outer"):
        with trace.span("inner", kind=trace.LLM):
            trace.count(prompt_tokens=10, completion_tokens=3)
            trace.count(prompt_tokens=5)
            time.sleep(0.01)
        trace.event("retry", "HTTP 429")
    spans = {s["name"]: s for s in tr.to_list()}
    assert spans["outer"]["parent"] is None
    assert spans["inner"]["parent"] == spans["outer"]["id"]
    assert spans["retry"]["parent"] == spans["outer"]["id"]
    assert spans["retry"]["kind"] == trace.EVENT and spans["retry"]["status"] == "warn"
    assert spans["inner"]["ms"] >= 10 and spans["outer"]["ms"] >= spans["inner"]["ms"]
    assert spans["inner"]["data"] == {"prompt_tokens": 15, "completion_tokens": 3}
    assert tr.totals() == {"llm_calls": 1, "prompt_tokens": 15, "completion_tokens": 3}


def test_laps_are_consecutive_siblings() -> None:
    with trace.recording() as tr, trace.span("rank"):
        lap = trace.Laps()
        lap("one")
        with trace.span("child"):
            pass
        lap.note("done")
        lap("two")
        lap.done()
    spans = {s["name"]: s for s in tr.to_list()}
    assert spans["one"]["parent"] == spans["two"]["parent"] == spans["rank"]["id"]
    assert spans["child"]["parent"] == spans["one"]["id"]
    assert spans["one"]["detail"] == "done"
    assert spans["two"]["start_ms"] >= spans["one"]["start_ms"] + spans["one"]["ms"]


def test_exception_marks_error_and_open_spans() -> None:
    with trace.recording() as tr:
        with pytest.raises(ValueError), trace.span("boom"):
            raise ValueError("x")
        lap = trace.Laps()
        lap("left open")
    spans = {s["name"]: s for s in tr.to_list()}
    assert spans["boom"]["status"] == "error"
    assert spans["left open"]["status"] == "error"
