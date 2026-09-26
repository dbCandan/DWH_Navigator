"""Judge benchmark: accuracy AND consistency per (model, temperature).

Same fixed candidate lists for every configuration (golden ask items incl. the scope
variant + negatives), each case judged ``RUNS`` times. Results are merged into
eval/bench_judge.json, so models can be added later.

Usage (LM Studio server running, dense index built):
    .venv/Scripts/python eval/bench_judge.py MODEL [MODEL ...] [--temps 0.1,0] [--runs 2]
Loads each model with GPU offload and unloads it afterwards (the embedding model stays).
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.WARNING)
from vsa.config import load_settings  # noqa: E402
from vsa.evaluation import restricted_engine  # noqa: E402
from vsa.llm.client import OpenAICompatibleClient  # noqa: E402
from vsa.llm.judge import judge  # noqa: E402
from vsa.pipeline import Engine  # noqa: E402
from vsa.scoring.combine import combine  # noqa: E402

LMS = str(Path.home() / ".lmstudio" / "bin" / "lms.exe")
OUT = Path("eval/bench_judge.json")
NEG_PICK = 0.5  # a negative case is answered correctly when no pick reaches this confidence


def lms(*args: str) -> str:
    r = subprocess.run([LMS, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout + r.stderr)[-300:]


def build_cases(engine: Engine, k: int) -> list[dict[str, Any]]:
    gold = yaml.safe_load(Path("tests/golden_set.yaml").read_text(encoding="utf-8"))
    negs = yaml.safe_load(Path("tests/negative_set.yaml").read_text(encoding="utf-8"))
    cases = []
    for g in gold:
        if g.get("mode", "ask") != "ask":
            continue
        prefix = (g.get("scope") or {}).get("exclude_object_prefix")
        eng = restricted_engine(engine, prefix) if prefix else engine
        ranked, _ = eng.rank_objects(g["query"], use_llm=False)
        cases.append({"id": g["id"], "query": g["query"], "expected": g["expected_objects"],
                      "primary": g.get("primary_object"), "cands": ranked[:k]})
    for n in negs[:3]:
        ranked, _ = engine.rank_objects(n["query"], use_llm=False)
        cases.append({"id": n["id"], "query": n["query"], "expected": [], "primary": None, "cands": ranked[:k]})
    return cases


def run_case(case: dict[str, Any], client: OpenAICompatibleClient, w_rule: float, w_llm: float) -> dict[str, Any]:
    t = time.time()
    r = judge(case["query"], case["cands"], client)
    sec = time.time() - t
    rule = {m.object_key: m.score for m in case["cands"]}
    conf = {k: v.confidence for k, v in r.verdicts.items()} if r else {}
    final = sorted(rule, key=lambda k: (-combine(rule[k], conf.get(k, 0.0), w_rule, w_llm), k))
    picks = sorted(conf, key=lambda k: -conf[k])
    if case["expected"]:
        judge_ok = bool(picks) and picks[0] in case["expected"]
        final_ok = final[0] in case["expected"]
    else:
        judge_ok = not picks or conf[picks[0]] < NEG_PICK
        final_ok = judge_ok
    return {"sec": round(sec, 1), "valid": r is not None, "unknown": r.unknown_ids if r else 0,
            "conf": {k.rsplit(".", 1)[-1]: round(v, 3) for k, v in conf.items()},
            "picks": [p.rsplit(".", 1)[-1] for p in picks], "final": [f.rsplit(".", 1)[-1] for f in final[:5]],
            "judge_ok": judge_ok, "final_ok": final_ok}


def summarize(rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    flat = [r for runs in rows.values() for r in runs]
    same_final = sum(1 for runs in rows.values() if all(r["final"] == runs[0]["final"] for r in runs))
    same_picks = sum(1 for runs in rows.values() if all(r["picks"] == runs[0]["picks"] for r in runs))
    drift = []
    for runs in rows.values():
        keys = set().union(*(r["conf"] for r in runs))
        for key in keys:
            vals = [r["conf"].get(key, 0.0) for r in runs]
            drift.append(max(vals) - min(vals))
    n = len(rows)
    return {
        "valid_json": round(sum(r["valid"] for r in flat) / len(flat), 3),
        "judge_accuracy": round(sum(r["judge_ok"] for r in flat) / len(flat), 3),
        "final_accuracy": round(sum(r["final_ok"] for r in flat) / len(flat), 3),
        "consistent_final_order": round(same_final / n, 3),
        "consistent_picks": round(same_picks / n, 3),
        "mean_conf_drift": round(statistics.mean(drift), 4) if drift else 0.0,
        "max_conf_drift": round(max(drift), 4) if drift else 0.0,
        "mean_sec": round(statistics.mean(r["sec"] for r in flat), 1),
        "hallucinated_ids": sum(r["unknown"] for r in flat),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--temps", default="0.1,0")
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args()
    temps = [float(x) for x in args.temps.split(",")]

    s = load_settings()
    s.llm.enabled = False
    engine = Engine.from_index(s)  # embeddings still used for ranking
    cases = build_cases(engine, s.llm.judge_candidates)
    data: dict[str, Any] = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    for model in args.models:
        loaded = [ln.split()[0] for ln in lms("ps").splitlines() if ln and not ln.startswith(("IDENTIFIER", " "))]
        for other in loaded:
            if other != model and "embedding" not in other:
                lms("unload", other)
        t = time.time()
        # Loading an already-loaded model makes LM Studio start a second copy (":2").
        status = "zaten yüklü" if model in loaded else lms(
            "load", model, "--context-length", "8192", "--gpu", "max", "-y").strip()[-80:]
        print(f"\n===== {model}  load: {status} ({time.time() - t:.0f}s)", flush=True)
        for temp in temps:
            client = OpenAICompatibleClient(s.llm.endpoint, model, temperature=temp, timeout=900,
                                            reasoning_effort=s.llm.reasoning_effort)
            rows: dict[str, list[dict[str, Any]]] = {}
            for case in cases:
                for run in range(args.runs):
                    res = run_case(case, client, s.scoring.w_rule, s.scoring.w_llm)
                    rows.setdefault(case["id"], []).append(res)
                    print(f"  T={temp} {case['id']:12s} run{run + 1} {res['sec']:5.1f}s judge_ok={res['judge_ok']} "
                          f"final_ok={res['final_ok']} picks={res['picks'][:3]}", flush=True)
            summary = summarize(rows)
            print(f"  >>> {model} T={temp}: {summary}", flush=True)
            data.setdefault(model, {})[str(temp)] = {"summary": summary, "cases": rows}
            OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        lms("unload", model)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
