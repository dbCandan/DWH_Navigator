"""Model lab (ADR-025): fixed cases, reply scoring, consistency summary, ranking."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vsa import lab
from vsa.config import Settings
from vsa.pipeline import Engine

FULL = "EDWDM.CMP.vCardLimitFullness"
CREDIT = "EDWDM.CON.vCreditCardLimit"


def _engine(path: Path) -> Engine:
    s = Settings()
    s.dictionary.path = str(path)
    return Engine.from_dictionary_file(s)


def test_build_cases_groups_and_reachability(sample_dictionary_path: Path) -> None:
    golden = [
        {"id": "a1", "mode": "ask", "query": "kart limit doluluk oranı",
         "expected_objects": [FULL]},
        {"id": "a2", "mode": "ask", "query": "kart limit doluluk", "expected_objects": ["X.Y.yok"]},
        {"id": "b1", "mode": "batch", "context": "Kart özeti", "fields": [
            {"name": "Fullness", "description": "Limit doluluk oranı", "expected_objects": [FULL]},
            {"name": "Period", "description": "Dönem", "expected_objects": [FULL]},  # structural
            {"name": "Other", "description": "Doğrulanmamış alan"},  # no verified answer
        ]},
    ]  # fmt: skip
    negatives = [{"id": "n1", "query": "kart limit"}, {"id": "n2", "query": "uzay gemisi yakıtı"}]
    cases = lab.build_cases(_engine(sample_dictionary_path), golden, negatives, k=8)
    by_id = {c["id"]: c for c in cases}
    assert by_id["a1"]["reachable"] and by_id["a1"]["group"] == "ask"
    assert not by_id["a2"]["reachable"]  # expected table is not among the candidates
    assert by_id["b1.Fullness"]["group"] == "alan" and "Kart özeti" in by_id["b1.Fullness"]["query"]
    assert "b1.Period" not in by_id and "b1.Other" not in by_id
    assert by_id["n1"]["group"] == "negatif" and by_id["n1"]["reachable"]
    assert "n2" not in by_id  # no candidates at all: nothing for a judge to do


def _case(sample_dictionary_path: Path, expected: list[str]) -> dict[str, Any]:
    golden = [{"id": "a", "mode": "ask", "query": "kart limit doluluk oranı",
               "expected_objects": expected}]  # fmt: skip
    return lab.build_cases(_engine(sample_dictionary_path), golden, [], k=8)[0]


def test_score_reply_positive_and_negative(sample_dictionary_path: Path) -> None:
    case = _case(sample_dictionary_path, [FULL])
    good = lab.score_reply(case, {FULL: 0.9, CREDIT: 0.2}, 0, 3.0, 0.75, 0.25)
    assert good["judge_ok"] and good["final_ok"] and good["picks"][0] == "vCardLimitFullness"
    wrong = lab.score_reply(case, {CREDIT: 0.95}, 0, 3.0, 0.75, 0.25)
    assert not wrong["judge_ok"]
    broken = lab.score_reply(case, None, 0, 3.0, 0.75, 0.25)
    assert not broken["valid"] and not broken["judge_ok"]

    neg = {**case, "expected": []}
    assert lab.score_reply(neg, {}, 0, 1.0, 0.75, 0.25)["judge_ok"]  # nothing picked
    assert lab.score_reply(neg, {FULL: 0.3}, 0, 1.0, 0.75, 0.25)["judge_ok"]  # only weak
    assert not lab.score_reply(neg, {FULL: 0.8}, 0, 1.0, 0.75, 0.25)["judge_ok"]


def _row(picks: list[str], conf: dict[str, float], ok: bool = True) -> dict[str, Any]:
    return {"sec": 10, "valid": True, "unknown": 0, "conf": conf, "picks": picks,
            "final": picks, "judge_ok": ok, "final_ok": ok}  # fmt: skip


def test_summarize_consistency_and_counted_cases() -> None:
    rows = {
        "a": [_row(["x", "y"], {"x": 0.9, "y": 0.5}), _row(["y", "x"], {"x": 0.7, "y": 0.8})],
        "b": [_row(["z"], {"z": 0.6}), _row(["z"], {"z": 0.6})],
        "u": [_row([], {}, ok=False), _row([], {}, ok=False)],  # unreachable: not counted
    }
    s = lab.summarize(rows, counted={"a", "b"})
    assert s["judge_accuracy"] == 1.0 and s["cases"] == 3
    assert s["consistent_picks"] == round(2 / 3, 3)  # "a" swapped its order
    assert s["max_conf_drift"] == 0.3 and s["valid_json"] == 1.0


def _summary(**kw: float) -> dict[str, float]:
    base = {"valid_json": 1.0, "judge_accuracy": 0.8, "final_accuracy": 1.0,
            "consistent_picks": 1.0, "consistent_final_order": 1.0, "mean_conf_drift": 0.0,
            "max_conf_drift": 0.0, "mean_sec": 40.0, "hallucinated_ids": 0,
            "cases": 10}  # fmt: skip
    return {**base, **kw}


def test_quality_disqualifies_invalid_or_invented_ids() -> None:
    assert lab.quality(_summary()) > 0.8
    assert lab.quality(_summary(valid_json=0.95)) == 0.0
    assert lab.quality(_summary(hallucinated_ids=1)) == 0.0
    assert lab.quality(_summary(mean_conf_drift=0.1)) < lab.quality(_summary())


def test_rank_prefers_faster_within_tie_else_quality() -> None:
    results = {
        "slow-good": {"T0|none": {"temperature": 0.0, "reasoning_effort": "none",
                                  "summary": _summary(mean_sec=90)}},
        "fast-same": {"T0|none": {"temperature": 0.0, "reasoning_effort": "none",
                                  "summary": _summary(mean_sec=20, mean_conf_drift=0.02)}},
        "fast-bad": {"T0|low": {"temperature": 0.0, "reasoning_effort": "low",
                                "summary": _summary(mean_sec=5, judge_accuracy=0.4)}},
        "broken": {"load_error": {"error": "sığmadı"}},
    }  # fmt: skip
    rows = lab.rank(results)
    assert [r["model"] for r in rows] == ["fast-same", "slow-good", "fast-bad"]
    assert rows[0]["recommended"] and not rows[1]["recommended"]
    results["fast-same"]["T0|none"]["summary"] = _summary(mean_sec=20, judge_accuracy=0.6)
    assert lab.rank(results)[0]["model"] == "slow-good"  # gap beyond TIE: quality wins


def test_pick_effort_first_usable_mode() -> None:
    tried: list[str] = []

    def probe(effort: str) -> bool:
        tried.append(effort)
        return effort == "low"

    assert lab.pick_effort(probe) == "low" and tried == ["none", "low"]
    assert lab.pick_effort(lambda e: False) is None
