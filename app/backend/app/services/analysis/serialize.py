"""An answer as the result envelope carries it (question-analysis Requirement 7).

The source's ``vsa.web.serialize`` (``76e21a3``) field for field: the result of a completed analysis
job is this form of the answer. ``report_id`` is gone (the report is fetched with the job's id) and
the term-list rows belong to list-search.
"""

from __future__ import annotations

from typing import Any

from app.domain.analysis import AnalysisResult, ColumnHit, DictColumn, ObjectMatch


def column(col: DictColumn) -> dict[str, Any]:
    return {
        "key": col.key,
        "column": col.column,
        "object": col.object_key,
        "description": col.description,
        "synonyms": list(col.synonyms),
        "pii": col.has_pii,
        "group": col.dataset_group,
    }


def hit(h: ColumnHit) -> dict[str, Any]:
    return {
        **column(h.col),
        "role": h.role,
        "signals": h.signals,
        "caveats": h.caveats,
    }


def match(m: ObjectMatch, rank: int = 0) -> dict[str, Any]:
    return {
        "rank": rank,
        "key": m.object_key,
        "database": m.database,
        "schema": m.schema,
        "name": m.object_name,
        "groups": m.dataset_groups,
        "score": round(m.score, 4),
        "level": m.level.value,
        "llm": None if m.llm_confidence is None else round(m.llm_confidence, 4),
        "components": {k: round(v, 4) for k, v in m.components.items()},
        "covered": m.covered,
        "missing": m.missing,
        "long_format": m.long_format_values,
        "dimension": m.dimension_column,
        "reason": m.reason,
        "caveat": [] if m.caveat == "-" else [c for c in m.caveat.split("\n") if c],
        "usage": m.usage,
        "covers": m.covers,
        "columns": [hit(h) for h in m.columns],
    }


def analysis(r: AnalysisResult) -> dict[str, Any]:
    return {
        "query": r.query,
        "verdict": r.verdict.value,
        "summary": r.summary,
        "objects": [match(m, i) for i, m in enumerate(r.objects, 1)],
        "near": [match(m) for m in r.near_misses],
        "notes": [{"scope": n.scope, "title": n.title, "text": n.text} for n in r.notes],
        "concepts": r.concepts,
        "expansion": r.expansion_terms,
        "method": r.method,
        "elapsed_ms": r.elapsed_ms,
        "dictionary_version": r.dictionary_version,
        "llm_model": r.llm_model,
        "analyst": r.analyst,
        "fallback": r.fallback,
        "interpretation": r.interpretation,
        "design": r.design,
        "attention": r.attention,
        "reused": reused(r),
        "missing": r.missing,
    }


def reused(r: AnalysisResult) -> dict[str, str] | None:
    """ADR-035: when and to which question an earlier answer was written; None if fresh."""
    if not r.reused_at:
        return None
    return {"at": r.reused_at, "query": r.reused_query, "match": r.reused_match}
