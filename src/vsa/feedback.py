"""Feedback loop, first step (HANDOVER §17 M7). Does file I/O.

Thumbs from the web UI land in ``data/feedback.jsonl``. This module turns them into
*candidate* golden-set items for review — they are not added to the golden set
automatically, because only verified requests belong there (§13.3).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class QueryFeedback:
    query: str
    up: list[str] = field(default_factory=list)
    down: list[str] = field(default_factory=list)
    fields: dict[str, dict[str, list[str]]] = field(default_factory=dict)  # batch: field -> votes


def load_feedback(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[QueryFeedback]:
    """Latest vote per (query, field, object) wins."""
    latest: dict[tuple[str, str, str], str] = {}
    for r in rows:
        latest[(r.get("query", ""), r.get("field", ""), r.get("object", ""))] = r.get("vote", "")
    by_query: dict[str, QueryFeedback] = {}
    for (query, fld, obj), vote in latest.items():
        fb = by_query.setdefault(query, QueryFeedback(query))
        if fld:
            votes = fb.fields.setdefault(fld, defaultdict(list))
            votes[vote].append(obj)
        elif vote == "up":
            fb.up.append(obj)
        elif vote == "down":
            fb.down.append(obj)
    return list(by_query.values())


def golden_candidates(summary: list[QueryFeedback]) -> list[dict[str, Any]]:
    today = date.today().isoformat()
    items: list[dict[str, Any]] = []
    for i, fb in enumerate((s for s in summary if s.up), 1):
        item: dict[str, Any] = {
            "id": f"fb-{today}-{i:02d}",
            "query": fb.query,
            "mode": "ask",
            "expected_objects": sorted(fb.up),
            "source": f"geri-bildirim-{today}",
            "notes": "Arayüz geri bildiriminden aday; doğrulanınca golden_set.yaml'a taşıyın.",
        }
        if fb.down:
            item["rejected_objects"] = sorted(fb.down)
        items.append(item)
    return items


def export_candidates(feedback_path: Path, out_path: Path) -> int:
    items = golden_candidates(summarize(load_feedback(feedback_path)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "# Golden set ADAYLARI — gözden geçirip doğrulananları tests/golden_set.yaml'a ekleyin.\n"
        + yaml.safe_dump(items, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    return len(items)
