"""Model lab: which chat model / temperature / reasoning mode makes the best judge?

Pure logic — building the fixed test cases, scoring one judge reply, summarising runs and
ranking configurations. The orchestration (loading models in LM Studio, timing, files)
lives in ``vsa lab`` (cli.py). ADR-025.

Every configuration sees the *same* candidate lists (rule + dense ranking, LLM off), so
differences come from the judge alone. Each case is judged ``runs`` times to measure
consistency: same picks, same final order, confidence drift.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from vsa.evaluation import restricted_engine
from vsa.models import ObjectMatch
from vsa.pipeline import Engine
from vsa.scoring.combine import combine

RESULTS_PATH = Path("eval/lab.json")  # summaries + per-run replies, merged across runs
PROGRESS_PATH = Path("data/lab_progress.json")  # live state for the settings screen
STOP_PATH = Path("data/lab_stop")  # created by the screen: stop after the current call

NEG_PICK = 0.5  # a negative case is right when no pick reaches this confidence
EFFORTS = ("none", "low", "")  # reasoning modes tried in order; "" = not sent

# Composite quality: judge accuracy weighs most (it is what the model adds), then the
# final order the user sees, then run-to-run stability. Confidence drift is a penalty.
W_JUDGE, W_FINAL, W_PICKS, W_ORDER, W_DRIFT = 0.45, 0.25, 0.15, 0.15, 0.5
TIE = 0.02  # quality gap within which the faster configuration wins
STRUCTURAL_FIELDS = ("CustomerId", "Period")


def build_cases(
    engine: Engine,
    golden: Sequence[Mapping[str, Any]],
    negatives: Sequence[Mapping[str, Any]],
    k: int,
) -> list[dict[str, Any]]:
    """Fixed judge inputs: golden ask items, verified batch fields as requests, negatives."""
    cases: list[dict[str, Any]] = []

    def add(cid: str, group: str, query: str, expected: Sequence[str], eng: Engine) -> None:
        ranked, _ = eng.rank_objects(query, use_llm=False)
        cands = ranked[:k]
        if not cands:
            return  # nothing to judge (the rule layer already answers "bulunamadı")
        reachable = not expected or any(m.object_key in expected for m in cands)
        cases.append({"id": cid, "group": group, "query": query, "expected": list(expected),
                      "reachable": reachable, "cands": cands})

    for g in golden:
        mode = g.get("mode", "ask")
        if mode == "ask":
            prefix = (g.get("scope") or {}).get("exclude_object_prefix")
            eng = restricted_engine(engine, prefix) if prefix else engine
            add(str(g["id"]), "ask", str(g["query"]), g.get("expected_objects") or [], eng)
        elif mode == "batch":
            context = str(g.get("context", ""))
            for f in g.get("fields", []):
                expected = f.get("expected_objects") or []
                # Structural fields (customer no, period) fit dozens of tables — not a
                # judge question on their own.
                if not expected or f.get("name") in STRUCTURAL_FIELDS:
                    continue
                query = f"{f.get('description', '')} ({context})"
                add(f"{g['id']}.{f['name']}", "alan", query, expected, engine)
    for n in negatives:
        add(str(n["id"]), "negatif", str(n["query"]), [], engine)
    return cases


def score_reply(
    case: Mapping[str, Any],
    conf: Mapping[str, float] | None,
    unknown_ids: int,
    seconds: float,
    w_rule: float,
    w_llm: float,
) -> dict[str, Any]:
    """One judge reply against the case. ``conf`` is None when the reply was unusable."""
    cands: Sequence[ObjectMatch] = case["cands"]
    rule = {m.object_key: m.score for m in cands}
    c = dict(conf or {})
    final = sorted(rule, key=lambda key: (-combine(rule[key], c.get(key, 0.0), w_rule, w_llm), key))
    picks = sorted(c, key=lambda key: (-c[key], key))
    expected = case["expected"]
    if expected:
        judge_ok = bool(picks) and picks[0] in expected
        final_ok = bool(final) and final[0] in expected
    else:
        judge_ok = not picks or c[picks[0]] < NEG_PICK
        final_ok = judge_ok
    return {
        "sec": round(seconds, 1),
        "valid": conf is not None,
        "unknown": unknown_ids,
        "conf": {k.rsplit(".", 1)[-1]: round(v, 3) for k, v in c.items()},
        "picks": [p.rsplit(".", 1)[-1] for p in picks],
        "final": [f.rsplit(".", 1)[-1] for f in final[:5]],
        "judge_ok": judge_ok,
        "final_ok": final_ok,
    }


def summarize(rows: Mapping[str, Sequence[Mapping[str, Any]]], counted: set[str]) -> dict[str, Any]:
    """Accuracy over ``counted`` cases (reachable ones); consistency over all cases."""
    flat = [r for cid, runs in rows.items() if cid in counted for r in runs]
    every = [r for runs in rows.values() for r in runs]
    n = len(rows) or 1

    def stable(key: str) -> int:
        return sum(1 for runs in rows.values() if all(r[key] == runs[0][key] for r in runs))

    same_final, same_picks = stable("final"), stable("picks")
    drift: list[float] = []
    for runs in rows.values():
        keys: set[str] = set().union(*(r["conf"] for r in runs))
        for key in keys:
            vals = [r["conf"].get(key, 0.0) for r in runs]
            drift.append(max(vals) - min(vals))

    def rate(items: Sequence[Mapping[str, Any]], key: str) -> float:
        return round(sum(bool(r[key]) for r in items) / len(items), 3) if items else 0.0

    return {
        "cases": len(rows),
        "valid_json": rate(every, "valid"),
        "judge_accuracy": rate(flat, "judge_ok"),
        "final_accuracy": rate(flat, "final_ok"),
        "consistent_final_order": round(same_final / n, 3),
        "consistent_picks": round(same_picks / n, 3),
        "mean_conf_drift": round(statistics.mean(drift), 4) if drift else 0.0,
        "max_conf_drift": round(max(drift), 4) if drift else 0.0,
        "mean_sec": round(statistics.mean(r["sec"] for r in every), 1) if every else 0.0,
        "hallucinated_ids": sum(int(r["unknown"]) for r in every),
    }


def quality(s: Mapping[str, Any]) -> float:
    """Composite 0..1 quality of a configuration (speed is only a tie-breaker)."""
    if s.get("valid_json", 0) < 1 or s.get("hallucinated_ids", 0):
        return 0.0  # unusable replies or invented ids disqualify (ADR-002)
    q = (
        W_JUDGE * s["judge_accuracy"]
        + W_FINAL * s["final_accuracy"]
        + W_PICKS * s["consistent_picks"]
        + W_ORDER * s["consistent_final_order"]
        - W_DRIFT * s["mean_conf_drift"]
    )
    return round(max(0.0, float(q)), 4)


def rank(results: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Flatten ``{model: {config_key: {summary, …}}}`` into rows, best first."""
    rows: list[dict[str, Any]] = []
    for model, configs in results.items():
        for entry in configs.values():
            if "summary" not in entry:
                continue
            s = entry["summary"]
            rows.append({
                "model": model,
                "temperature": entry.get("temperature", 0.0),
                "reasoning_effort": entry.get("reasoning_effort", "none"),
                "quality": quality(s),
                "at": entry.get("at", ""),
                "size_gb": entry.get("size_gb", 0),
                **s,
            })
    best_q = max((r["quality"] for r in rows), default=0.0)

    def key(r: Mapping[str, Any]) -> tuple[int, float, float]:
        # Within TIE of the best, the faster one wins; otherwise quality decides.
        near = r["quality"] >= best_q - TIE and r["quality"] > 0
        return (0 if near else 1, r["mean_sec"] if near else -r["quality"], -r["quality"])

    rows.sort(key=key)
    for i, r in enumerate(rows):
        r["recommended"] = i == 0 and r["quality"] > 0
    return rows


def pick_effort(probe: Callable[[str], bool]) -> str | None:
    """First reasoning mode for which the model returns a usable judge reply."""
    for effort in EFFORTS:
        if probe(effort):
            return effort
    return None
