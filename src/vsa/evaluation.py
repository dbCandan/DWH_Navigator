"""Evaluation (HANDOVER §13, M2).

Three item groups:

* **ask**   — free-text requests. Hit at k when ANY ``expected_objects`` is in the top k
  (several answers can be right, Ek A.1); ``primary_object`` tracks the manual first
  choice. Also column recall and trap checks (Ek A.2).
* **batch** — fields of a target-table request (Ek A.3), each asked as
  "<field> — <context>". Early M5 signal.
* **negative** — requests with no answer in the dictionary; anything but
  BULUNAMADI is a false answer (ADR-006).

Items with ``scope.exclude_object_prefix`` run against a dictionary without those
objects. The app itself has no filter (ADR-001); this simulates a separate file.
"""

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from vsa.expansion.query_expander import QueryExpander
from vsa.models import Dictionary, ObjectMatch, Verdict
from vsa.pipeline import Engine
from vsa.text.normalize import split_camel

KS = (1, 3, 5)
COLUMN_WINDOW = 5  # expected columns are looked for in the top-N objects' listed fields
TRAP_WINDOW = 3


@dataclass(slots=True)
class ItemResult:
    id: str
    group: str  # "ask" | "batch"
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
        for g in ("ask", "batch"):
            if not self.group(g):
                continue
            for k in KS:
                out[f"{g}.recall@{k}"] = round(self.recall(k, g), 4)
            out[f"{g}.mrr"] = round(self.mrr(g), 4)
            out[f"{g}.column_recall"] = round(self.column_recall(g), 4)
            out[f"{g}.n"] = len(self.group(g))
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


def field_query(context: str, name: str) -> str:
    """Batch field as a request: "Distinct Bank Count — Müşteri bazında … özeti"."""
    return f"{' '.join(split_camel(name))} — {context}"


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
    return Engine(dictionary, engine.settings, engine.resources)


def with_expansion(engine: Engine, terms: bool, synonyms: bool) -> Engine:
    """Cheap variant of an engine with other expansion switches (index reused)."""
    variant = copy.copy(engine)
    variant.expander = QueryExpander(
        engine.resources.term_groups,
        engine.features,
        engine.resources.stopwords,
        expansion_weight=engine.settings.expansion.weight,
        enabled=terms,
        use_synonyms=synonyms,
    )
    return variant


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
    ranked: list[ObjectMatch],
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
        mode = item.get("mode", "ask")
        eng = engine_for(item)
        if mode == "ask":
            q = str(item["query"])
            report.items.append(
                _score_item(str(item["id"]), "ask", q, eng.rank_objects(q)[0], item)
            )
        elif mode == "batch":
            for fld in item["fields"]:
                q = field_query(str(item["context"]), str(fld["name"]))
                report.items.append(
                    _score_item(
                        f"{item['id']}.{fld['name']}", "batch", q, eng.rank_objects(q)[0], fld
                    )
                )

    for neg in negatives:
        result = engine.analyze(str(neg["query"]))
        pool = result.objects or result.near_misses
        report.negatives.append(
            NegativeResult(
                id=str(neg["id"]),
                query=str(neg["query"]),
                verdict=result.verdict,
                top_object=pool[0].object_name if pool else "-",
                top_score=pool[0].score if pool else 0.0,
            )
        )
    return report


# --------------------------------------------------------------------------- comparison


EXPANSION_CONFIGS: tuple[tuple[str, bool, bool], ...] = (
    ("Genişletmesiz BM25", False, False),
    ("+ kurumsal terim sözlüğü", True, False),
    ("+ sözlük içi eş anlamlılar", True, True),
    ("Yalnız sözlük eş anlamlıları", False, True),
)


def compare_configs(
    engine: Engine,
    golden: Sequence[dict[str, Any]],
    negatives: Sequence[dict[str, Any]] = (),
    progress: Callable[[str], None] | None = None,
) -> list[tuple[str, EvalReport]]:
    """HANDOVER §13.4 — the expansion configurations that exist so far (M3/M4 add more)."""
    out = []
    for name, terms, synonyms in EXPANSION_CONFIGS:
        if progress:
            progress(name)
        out.append((name, evaluate(with_expansion(engine, terms, synonyms), golden, negatives)))
    return out


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
