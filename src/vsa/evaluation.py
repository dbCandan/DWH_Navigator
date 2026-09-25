"""Golden-set evaluation (HANDOVER §13): recall@1/3/5 and MRR.

A query counts as a hit at k when ANY of its ``expected_objects`` is in the top k —
some requests have several correct answers depending on scope (Ek A.1).
``primary_object`` additionally tracks the manual analysis' first choice.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from vsa.pipeline import Engine

KS = (1, 3, 5)


@dataclass(slots=True)
class ItemResult:
    id: str
    query: str
    rank: int | None  # 1-based rank of the first expected object; None = not in list
    primary_rank: int | None
    top: list[str]


@dataclass(slots=True)
class EvalReport:
    items: list[ItemResult] = field(default_factory=list)

    def recall(self, k: int) -> float:
        if not self.items:
            return 0.0
        return sum(1 for i in self.items if i.rank is not None and i.rank <= k) / len(self.items)

    @property
    def mrr(self) -> float:
        if not self.items:
            return 0.0
        return sum(1 / i.rank for i in self.items if i.rank) / len(self.items)

    def as_dict(self) -> dict[str, float]:
        out = {f"recall@{k}": self.recall(k) for k in KS}
        out["mrr"] = self.mrr
        return out


def load_golden(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    assert isinstance(data, list)
    return data


def _rank(ranked: Sequence[str], wanted: Sequence[str]) -> int | None:
    for pos, key in enumerate(ranked, 1):
        if key in wanted:
            return pos
    return None


def evaluate(engine: Engine, golden: Sequence[dict[str, Any]]) -> EvalReport:
    report = EvalReport()
    for item in golden:
        if item.get("mode", "ask") != "ask":
            continue
        ranked = [m.object_key for m in engine.rank_objects(item["query"])[0]]
        expected = list(item.get("expected_objects", []))
        primary = item.get("primary_object")
        report.items.append(
            ItemResult(
                id=str(item["id"]),
                query=str(item["query"]),
                rank=_rank(ranked, expected),
                primary_rank=_rank(ranked, [primary]) if primary else None,
                top=ranked[:5],
            )
        )
    return report
