"""Evaluation (HANDOVER §13, M2).

Two item groups:

* **ask**   — free-text requests (the analyst answer when the model is on, ADR-029).
  Hit at k when ANY ``expected_objects`` is in the top k
  (several answers can be right, Ek A.1); ``primary_object`` tracks the manual first
  choice. Also column recall and trap checks (Ek A.2).
* **negative** — requests with no answer in the dictionary; anything but
  BULUNAMADI is a false answer (ADR-006).

Golden items of the removed target-table mode (``mode: batch``, ADR-033) stay in the
file — items are never deleted — but are skipped.

Items with ``scope.exclude_object_prefix`` run against a dictionary without those
objects. The app itself has no filter (ADR-001); this simulates a separate file.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from vsa.models import Dictionary, ObjectMatch, Verdict
from vsa.pipeline import Engine

KS = (1, 3, 5)
COLUMN_WINDOW = 5  # expected columns are looked for in the top-N objects' listed fields
TRAP_WINDOW = 3


@dataclass(slots=True)
class ItemResult:
    id: str
    group: str  # "ask"
    query: str
    rank: int | None  # 1-based rank of the first expected object; None = not ranked
    primary_rank: int | None
    top: list[str]
    columns_found: int = 0
    columns_total: int = 0
    trap_violations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NegativeResult:
    id: str
    query: str
    verdict: Verdict
    top_object: str
    top_score: float

    @property
    def false_answer(self) -> bool:
        return self.verdict is not Verdict.NOT_FOUND


@dataclass(slots=True)
class EvalReport:
    items: list[ItemResult] = field(default_factory=list)
    negatives: list[NegativeResult] = field(default_factory=list)

    def group(self, name: str) -> list[ItemResult]:
        return [i for i in self.items if i.group == name]

    def recall(self, k: int, group: str = "ask") -> float:
        items = self.group(group)
        if not items:
            return 0.0
        return sum(1 for i in items if i.rank is not None and i.rank <= k) / len(items)

    def mrr(self, group: str = "ask") -> float:
        items = self.group(group)
        if not items:
            return 0.0
        return sum(1 / i.rank for i in items if i.rank) / len(items)

    def column_recall(self, group: str = "ask") -> float:
        items = [i for i in self.group(group) if i.columns_total]
        total = sum(i.columns_total for i in items)
        return sum(i.columns_found for i in items) / total if total else 0.0

    @property
    def trap_violations(self) -> int:
        return sum(len(i.trap_violations) for i in self.items)

    @property
    def false_answer_rate(self) -> float:
        if not self.negatives:
            return 0.0
        return sum(n.false_answer for n in self.negatives) / len(self.negatives)

    def as_dict(self) -> dict[str, float]:
        out: dict[str, float] = {}
        if self.group("ask"):
            for k in KS:
                out[f"ask.recall@{k}"] = round(self.recall(k), 4)
            out["ask.mrr"] = round(self.mrr(), 4)
            out["ask.column_recall"] = round(self.column_recall(), 4)
            out["ask.n"] = len(self.group("ask"))
        out["trap_violations"] = self.trap_violations
        if self.negatives:
            out["negative.false_answer_rate"] = round(self.false_answer_rate, 4)
            out["negative.n"] = len(self.negatives)
        return out


# --------------------------------------------------------------------------- inputs


def load_yaml_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    assert isinstance(data, list)
    return data


load_golden = load_yaml_list


def restricted_engine(engine: Engine, exclude_object_prefix: str) -> Engine:
    """Engine over a dictionary without objects starting with the prefix (ADR-001)."""
    kept = [
        c for c in engine.dictionary.columns if not c.object_name.startswith(exclude_object_prefix)
    ]
    dictionary = Dictionary(
        columns=[replace(c, id=i) for i, c in enumerate(kept)],
        source_path=engine.dictionary.source_path,
        version=f"{engine.dictionary.version}-excl-{exclude_object_prefix}",
    )
    return Engine(dictionary, engine.settings, engine.resources, llm=engine.llm)


# --------------------------------------------------------------------------- scoring


def _rank(ranked: Sequence[str], wanted: Iterable[str]) -> int | None:
    wanted = set(wanted)
    for pos, key in enumerate(ranked, 1):
        if key in wanted:
            return pos
    return None


def _score_item(
    item_id: str,
    group: str,
    query: str,
    ranked: Sequence[ObjectMatch],
    spec: dict[str, Any],
) -> ItemResult:
    keys = [m.object_key for m in ranked]
    primary = spec.get("primary_object")
    listed = {h.col.key for m in ranked[:COLUMN_WINDOW] for h in m.columns}
    expected_cols = list(spec.get("expected_columns", []))

    violations: list[str] = []
    for trap in spec.get("traps", []):
        col, rule = trap["column"], trap["rule"]
        if rule == "not_lead":
            if any(m.columns and m.columns[0].col.key == col for m in ranked[:TRAP_WINDOW]):
                violations.append(f"{col}: ilk {TRAP_WINDOW} öneride lider kolon")
        elif rule == "caveat":
            for m in ranked[:COLUMN_WINDOW]:
                for h in m.columns:
                    if h.col.key == col and not h.caveats:
                        violations.append(f"{col}: kısıt notu olmadan listelendi")
        else:
            raise ValueError(f"Bilinmeyen tuzak kuralı: {rule}")

    return ItemResult(
        id=item_id,
        group=group,
        query=query,
        rank=_rank(keys, spec.get("expected_objects", [])),
        primary_rank=_rank(keys, [primary]) if primary else None,
        top=keys[:5],
        columns_found=sum(1 for c in expected_cols if c in listed),
        columns_total=len(expected_cols),
        trap_violations=violations,
    )


def evaluate(
    engine: Engine,
    golden: Sequence[dict[str, Any]],
    negatives: Sequence[dict[str, Any]] = (),
) -> EvalReport:
    report = EvalReport()
    scoped: dict[str, Engine] = {}

    def engine_for(item: dict[str, Any]) -> Engine:
        prefix = (item.get("scope") or {}).get("exclude_object_prefix")
        if not prefix:
            return engine
        if prefix not in scoped:
            scoped[prefix] = restricted_engine(engine, prefix)
        return scoped[prefix]

    for item in golden:
        if item.get("mode", "ask") != "ask":
            continue  # the target-table mode is gone (ADR-033); its items stay in the file
        eng = engine_for(item)
        q = str(item["query"])
        # The answer people see: the analyst's recommendations (ADR-029). Without a model
        # there is no answer (ADR-038); the rule ranking is measured instead — the hints
        # the analyst would get.
        ranked = eng.analyze(q).objects if eng.analyst_enabled else eng.rank_objects(q)[0]
        report.items.append(_score_item(str(item["id"]), "ask", q, ranked, item))

    for neg in negatives:
        query = str(neg["query"])
        answer = engine.analyze(query) if engine.analyst_enabled else engine.rule_answer(query)
        pool = answer.objects or answer.near_misses
        report.negatives.append(
            NegativeResult(
                id=str(neg["id"]),
                query=str(neg["query"]),
                verdict=answer.verdict,
                top_object=pool[0].object_name if pool else "-",
                top_score=pool[0].score if pool else 0.0,
            )
        )
    return report


# --------------------------------------------------------------------------- history


def _git_commit(cwd: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "-"


def append_history(
    report: EvalReport, path: Path, engine: Engine, label: str = ""
) -> dict[str, Any]:
    """Record metrics before/after a weight change (§9.7). One JSON object per line."""
    entry = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "commit": _git_commit(path.parent if path.parent.exists() else Path.cwd()),
        "label": label,
        "dictionary_version": engine.dictionary.version,
        "metrics": report.as_dict(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
