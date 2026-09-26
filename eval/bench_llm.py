"""Benchmark candidate chat models as the VSA judge (ADR-021).

Usage (LM Studio running, dense index built):
    .venv/Scripts/python eval/bench_llm.py [model-key ...]
(Unloads all models when done; reload them or run baslat.bat afterwards.)
"""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import yaml

logging.basicConfig(level=logging.WARNING)
from vsa.config import load_settings  # noqa: E402
from vsa.evaluation import restricted_engine  # noqa: E402
from vsa.llm.client import OpenAICompatibleClient  # noqa: E402
from vsa.llm.judge import judge  # noqa: E402
from vsa.pipeline import Engine  # noqa: E402

LMS = str(Path.home() / ".lmstudio" / "bin" / "lms.exe")
MODELS = sys.argv[1:] or ["qwen/qwen3.5-9b", "google/gemma-3-12b", "qwen/qwen3-coder-30b"]

s = load_settings()
s.llm.enabled = False  # rank without the judge; the judge is called explicitly below
engine = Engine.from_index(s)
gold = yaml.safe_load(open("tests/golden_set.yaml", encoding="utf-8"))
negs = yaml.safe_load(open("tests/negative_set.yaml", encoding="utf-8"))
cases = []
for g in gold:
    if g.get("mode", "ask") != "ask":
        continue
    eng = engine
    prefix = (g.get("scope") or {}).get("exclude_object_prefix")
    if prefix:
        eng = restricted_engine(engine, prefix)
    ranked, _ = eng.rank_objects(g["query"])
    cases.append({"id": g["id"], "query": g["query"], "expected": g["expected_objects"], "cands": ranked[:8]})
for n in negs[:3]:
    ranked, _ = engine.rank_objects(n["query"])
    cases.append({"id": n["id"], "query": n["query"], "expected": [], "cands": ranked[:8]})

results = {}
for model in MODELS:
    print(f"\n===== {model}", flush=True)
    subprocess.run([LMS, "unload", "--all"], capture_output=True)
    t = time.time()
    load = subprocess.run([LMS, "load", model, "--context-length", "8192", "--gpu", "max", "-y"], capture_output=True, text=True)
    print("load", round(time.time() - t, 1), "s", load.returncode, (load.stderr or "")[-200:].strip(), flush=True)
    client = OpenAICompatibleClient(s.llm.endpoint, model, timeout=600, temperature=0.1)
    rows = []
    for c in cases:
        t = time.time()
        r = judge(c["query"], c["cands"], client)
        dt = time.time() - t
        if r is None:
            rows.append({"id": c["id"], "sec": round(dt, 1), "ok": False})
            print(f"  {c['id']:12s} {dt:6.1f}s  FAILED", flush=True)
            continue
        picks = sorted(r.verdicts.items(), key=lambda kv: -kv[1].confidence)
        top = picks[0][0] if picks else None
        hit = (top in c["expected"]) if c["expected"] else (not picks or picks[0][1].confidence < 0.5)
        rows.append({
            "id": c["id"], "sec": round(dt, 1), "ok": True, "hit": hit, "unknown": r.unknown_ids,
            "picks": [(k.split(".")[-1], round(v.confidence, 2)) for k, v in picks],
            "reason": picks[0][1].reason if picks else "", "caveat": picks[0][1].caveat if picks else "",
        })
        print(f"  {c['id']:12s} {dt:6.1f}s  hit={hit}  picks={rows[-1]['picks'][:3]}", flush=True)
        if picks:
            print(f"      gerekçe: {picks[0][1].reason[:220]}", flush=True)
    results[model] = rows
    ok = [x for x in rows if x["ok"]]
    print(f"  SUMMARY valid={len(ok)}/{len(rows)} hits={sum(x.get('hit', False) for x in ok)} "
          f"mean={sum(x['sec'] for x in rows)/len(rows):.1f}s", flush=True)

Path("eval/bench_llm.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
subprocess.run([LMS, "unload", "--all"], capture_output=True)
print("DONE", flush=True)
