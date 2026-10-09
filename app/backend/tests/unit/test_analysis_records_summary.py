"""The administration figures are the source screen's (analysis-records Requirement 7, 15, 21,
Decision 7): ``quantile`` and the ``Analyses.kpi`` and ``perf`` sums, here written again from the
source's ``admin.html`` and compared on the same records."""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from typing import Any

import pytest

from app.services.analysis_records import quantile, summarize

pytestmark = pytest.mark.unit


def source_quantile(sorted_values: list[float], p: float) -> float:
    # admin.html: const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
    if not sorted_values:
        return 0
    i = (len(sorted_values) - 1) * p
    lo, hi = math.floor(i), math.ceil(i)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (i - lo)


@pytest.mark.parametrize("seed", range(20))
def test_quantile_is_the_sources(seed: int) -> None:
    rng = random.Random(seed)
    values = sorted(rng.randint(0, 600_000) for _ in range(rng.randint(1, 40)))
    for p in (0.5, 0.9, 0.0, 1.0):
        assert quantile(values, p) == source_quantile(values, p)
    assert quantile([], 0.5) == 0


def _figure(flow: str, verdict: str | None, ms: int, who: str, **phases: int) -> dict[str, Any]:
    figure: dict[str, Any] = {
        "flow": flow, "verdict": verdict, "duration_ms": ms, "asked_at": datetime.now(UTC),
        "llm_calls": 2, "prompt_tokens": 10, "completion_tokens": 3,
        "asker_public_id": who, "asker_display_name": who.upper(),
    }  # fmt: skip
    for name in ("queue", "saved_answer_lookup", "model_check", "rule_hints", "analyst_pick",
                 "analyst_write"):  # fmt: skip
        figure[f"phase_{name}_ms"] = phases.get(name, 0)
    return figure


def test_the_kpis_are_the_sources() -> None:
    rows = [
        _figure("analyst", "VAR", 40_000, "a", rule_hints=300, analyst_write=20_000),
        _figure("analyst", "KISMEN VAR", 90_000, "b", queue=500),
        _figure("reused", "VAR", 30, "a", saved_answer_lookup=25),
        _figure("unavailable", "BULUNAMADI", 200, "b"),
        _figure("failed", None, 100, "c"),
        _figure("interrupted", None, 0, "c"),
    ]
    out = summarize(rows)
    # Analyses.kpi: answered = with a verdict; found = answered but not BULUNAMADI.
    answered = [r for r in rows if r["verdict"]]
    assert out["with_result"] == len(answered)
    assert out["with_tables"] == len([r for r in answered if r["verdict"] != "BULUNAMADI"])
    analyst_ms = sorted(r["duration_ms"] for r in rows if r["flow"] == "analyst")
    assert out["analyst_p50_ms"] == source_quantile(analyst_ms, 0.5)
    assert out["analyst_p90_ms"] == source_quantile(analyst_ms, 0.9)
    # perf: averages over records whose phase is above zero; all durations for the spread.
    every = sorted(r["duration_ms"] for r in rows)
    assert (out["p50_ms"], out["p90_ms"], out["max_ms"]) == (
        source_quantile(every, 0.5), source_quantile(every, 0.9), every[-1]
    )  # fmt: skip
    phases = {p["phase"]: (p["average_ms"], p["count"]) for p in out["phases"]}
    assert phases["queue"] == (500, 1) and phases["model_check"] == (None, 0)
    assert phases["analyst_write"] == (20_000, 1)
    assert out["llm_calls"] == 12 and out["flows"]["interrupted"] == 1
    assert [(a["public_id"], a["count"]) for a in out["askers"]] == [("a", 2), ("b", 2), ("c", 2)]
