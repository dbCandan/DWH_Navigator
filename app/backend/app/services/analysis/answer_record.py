"""The full answer as the analysis record keeps it (question-analysis Requirement 18, Decision 10).

A saved answer keeps the source's form (``answer_cache.encode``): columns by key, rebuilt from the
current dictionary when the answer is given again. The analysis record must outlive the dictionary
it was answered from — the result envelope and the Excel report of an old analysis are made from
it after any later import — so its form is the same with each column's dictionary row inside.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from app.domain.analysis import AnalysisResult, DictColumn
from app.services.analysis import answer_cache

_COLUMN_FIELDS = frozenset(f.name for f in fields(DictColumn))


def _hits(matches: list[dict[str, Any]], replace: Any) -> list[dict[str, Any]]:
    return [
        {**m, "columns": [{**h, "col": replace(h["col"])} for h in m["columns"]]} for m in matches
    ]


def record_form(result: AnalysisResult) -> dict[str, Any]:
    """The answer with every column's dictionary row inside."""

    rows = {
        h.col.key: {**asdict(h.col), "synonyms": list(h.col.synonyms)}
        for m in (*result.objects, *result.near_misses)
        for h in m.columns
    }
    data = answer_cache.encode(result)
    return {
        **data,
        "objects": _hits(data["objects"], rows.__getitem__),
        "near_misses": _hits(data["near_misses"], rows.__getitem__),
    }


def from_record_form(data: dict[str, Any]) -> AnalysisResult | None:
    """The answer back from the record alone; None when the stored form does not fit. A row's
    fields the dictionary column no longer has are ignored, so older records stay readable."""

    try:
        columns: dict[str, DictColumn] = {}
        for m in (*data["objects"], *data["near_misses"]):
            for h in m["columns"]:
                row = h["col"]
                known = {k: v for k, v in row.items() if k in _COLUMN_FIELDS}
                column = DictColumn(**{**known, "synonyms": tuple(row["synonyms"])})
                columns[column.key] = column

        def key(row: dict[str, Any]) -> str:
            return f"{row['database']}.{row['schema']}.{row['object_name']}.{row['column']}"

        keyed = {
            **data,
            "objects": _hits(data["objects"], key),
            "near_misses": _hits(data["near_misses"], key),
        }
    except (KeyError, TypeError, ValueError):
        return None
    return answer_cache.decode(keyed, columns)
