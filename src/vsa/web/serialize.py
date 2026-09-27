"""Result objects -> JSON-ready dicts for the web UI."""

from __future__ import annotations

from typing import Any

from vsa.models import (
    AnalysisResult,
    BatchResult,
    ColumnHit,
    DictColumn,
    FieldCandidate,
    FieldResult,
    ObjectMatch,
)


def column(col: DictColumn) -> dict[str, Any]:
    return {
        "key": col.key,
        "column": col.column,
        "object": col.object_key,
        "description": col.description,
        "synonyms": list(col.synonyms),
        "flags": [{"kind": f.kind.value, "text": f.text} for f in col.flags],
        "pii": col.has_pii,
        "group": col.dataset_group,
    }


def hit(h: ColumnHit) -> dict[str, Any]:
    return {
        **column(h.col),
        "role": h.role,
        "score": round(h.rule_score, 4),
        "signals": h.signals,
        "caveats": h.caveats,
        "concepts": h.concepts,
        "derive": h.needs_derivation,
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
        "rule_score": None if m.rule_score is None else round(m.rule_score, 4),
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
        "mode": "ask",
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
        "dropped": r.dropped_by_validation,
        "analyst": r.analyst,
        "fallback": r.fallback,
        "interpretation": r.interpretation,
        "design": r.design,
        "attention": r.attention,
    }


def candidate(c: FieldCandidate, rank: int) -> dict[str, Any]:
    return {
        **match(c.match, rank),
        "field_score": round(c.score, 4),
        "in_core": c.in_core,
        "derivation": c.derivation,
        "notes": c.notes,
    }


def field_result(fr: FieldResult) -> dict[str, Any]:
    f = fr.field
    return {
        "index": f.index,
        "tr": f.tr,
        "en": f.en,
        "description": f.description,
        "status": fr.status.value,
        "candidates": [candidate(c, i) for i, c in enumerate(fr.candidates, 1)],
    }


def batch(r: BatchResult) -> dict[str, Any]:
    return {
        "mode": "batch",
        "name": r.name,
        "verdict": r.verdict.value,
        "summary": r.summary,
        "time_grain": r.time_grain,
        "fields": [field_result(fr) for fr in r.fields],
        "coverage": [
            {
                "key": c.object_key,
                "name": c.object_name,
                "fields": c.fields,
                "ready": c.ready,
                "partial": c.partial,
                "mean": round(c.mean_score, 4),
            }
            for c in r.coverage
        ],
        "notes": [{"scope": n.scope, "title": n.title, "text": n.text} for n in r.notes],
        "method": r.method,
        "elapsed_ms": r.elapsed_ms,
        "dictionary_version": r.dictionary_version,
    }
