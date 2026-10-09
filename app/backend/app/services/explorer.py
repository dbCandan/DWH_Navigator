"""The dictionary explorer's reading of the serving engine (data-dictionary 007-dictionary-explorer
Requirement 3, 10, 11, Decision 1).

The source's ``App._object_index``, ``App.galaxy``, ``App.objects`` and ``App.object_detail``
(``src/vsa/web/server.py``, ``76e21a3``) as pure functions of an engine: the same tables, the same
order and the same fields. The table index of an engine is built once and kept while that engine
serves. Nothing here takes a lock, writes anything or logs a text, a table or a column name.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.domain.turkish_text import fold
from app.services.analysis import serialize
from app.services.analysis.pipeline import Engine

EXPLORER_LIMIT = 60
EXPLORER_CONTENT_LIMIT = 25  # objects from the content (search pipeline) layer
MIN_CONTENT_QUERY = 3  # shorter input: name matching only
OTHER_GROUP = "Diğer"
_LAYER_ORDER = {"ad": 0, "içerik": 1, "kolon adı": 2}


@dataclass(frozen=True, slots=True)
class IndexedTable:
    """One table of the explorer index; ``folded``, ``folded_columns`` and ``column_names`` are
    the source's private ``_fold``, ``_cols`` and ``_colnames``."""

    key: str
    name: str
    schema: str
    columns: int
    groups: list[str]
    folded: str
    folded_columns: str
    column_names: list[str]

    def public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "schema": self.schema,
            "columns": self.columns,
            "groups": list(self.groups),
        }


def table_index(engine: Engine) -> list[IndexedTable]:
    """Every table of the engine, by name (Python's plain string order), ties in dictionary order."""

    rows: list[IndexedTable] = []
    for key, obj in engine.objects.items():
        first = obj.features[0].col
        groups = sorted({f.col.dataset_group for f in obj.features if f.col.dataset_group})
        rows.append(
            IndexedTable(
                key=key,
                name=first.object_name,
                schema=f"{first.database}.{first.schema}",
                columns=len(obj.features),
                groups=groups,
                folded=fold(f"{key} {' '.join(groups)}"),
                folded_columns=fold(" ".join(f.col.column for f in obj.features)),
                column_names=[f.col.column for f in obj.features],
            )
        )
    rows.sort(key=lambda r: str(r.name))
    return rows


def galaxy(rows: list[IndexedTable]) -> list[dict[str, Any]]:
    """Every table with its main dataset group: the star map."""

    return [
        {
            "key": r.key,
            "name": r.name,
            "schema": r.schema,
            "group": r.groups[0] if r.groups else OTHER_GROUP,
            "columns": r.columns,
        }
        for r in rows
    ]


def search_mode(query: str) -> str:
    """``browse`` (no text), ``name_only`` (too short for the content layer) or ``full``."""

    needle = fold(query.strip())
    if not needle:
        return "browse"
    return "full" if len(needle) >= MIN_CONTENT_QUERY else "name_only"


def search(engine: Engine, rows: list[IndexedTable], query: str) -> dict[str, Any]:
    """Every search layer except the chat model: name, content (the rule ranking) and column
    name, at most 60 tables, ordered by layer, score and name."""

    started = time.perf_counter()
    text = query.strip()
    needle = fold(text)
    if not needle:
        browse = [{**r.public(), "match": ""} for r in rows[:EXPLORER_LIMIT]]
        return {"query": "", "items": browse, "counts": {}, "concepts": [], "elapsed_ms": 0}

    items: dict[str, dict[str, Any]] = {}
    for r in rows:
        if needle in r.folded:
            items[r.key] = {**r.public(), "match": "ad"}

    concepts: list[str] = []
    if len(needle) >= MIN_CONTENT_QUERY:
        ranked, expanded = engine.rank_objects(text, limit=EXPLORER_CONTENT_LIMIT)
        concepts = [c.display() for c in expanded.concepts]
        by_key = {r.key: r for r in rows}
        for m in ranked:
            entry = items.get(m.object_key) or {**by_key[m.object_key].public(), "match": "içerik"}
            entry.update(
                score=round(m.score, 4),
                level=m.level.value,
                matched=[h.col.column for h in m.columns[:5]],
                covered=m.covered,
                missing=m.missing,
                signal=next((s for h in m.columns for s in h.signals), ""),
            )
            items[m.object_key] = entry

    for r in rows:
        if r.key in items or needle not in r.folded_columns:
            continue
        columns = [c for c in r.column_names if needle in fold(c)]
        items[r.key] = {**r.public(), "match": "kolon adı", "matched": columns[:5]}

    result = sorted(
        items.values(),
        key=lambda i: (_LAYER_ORDER[i["match"]], -float(i.get("score") or 0), str(i["name"])),
    )[:EXPLORER_LIMIT]
    counts: dict[str, int] = {}
    for i in result:
        counts[i["match"]] = counts.get(i["match"], 0) + 1
    return {
        "query": text,
        "items": result,
        "counts": counts,
        "concepts": concepts,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }


def table_detail(engine: Engine, key: str) -> dict[str, Any] | None:
    """A table's columns in dictionary order and its join keys; None when it is not served."""

    obj = engine.objects.get(key)
    if obj is None:
        return None
    first = obj.features[0].col
    return {
        "key": key,
        "name": first.object_name,
        "schema": f"{first.database}.{first.schema}",
        "groups": sorted({f.col.dataset_group for f in obj.features if f.col.dataset_group}),
        "columns": [serialize.column(f.col) for f in obj.features],
        "join_keys": engine.join_keys.get(key, []),
    }


class ExplorerIndex:
    """The serving engine's table index, built once per engine."""

    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._rows: list[IndexedTable] = []

    def rows(self, engine: Engine) -> list[IndexedTable]:
        if engine is not self._engine:
            self._rows = table_index(engine)
            self._engine = engine
        return self._rows
