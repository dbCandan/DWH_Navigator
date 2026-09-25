"""Object-level aggregation — THE core business rule (HANDOVER §8, ADR-005).

Search runs on columns, but the business unit asks for tables. A table wins not
because one column matches perfectly, but because it carries several of the
requested concepts together, with the right time axis and granularity:

    object_score = 0.50 × best_column + 0.30 × coverage
                 + 0.10 × time        + 0.10 × granularity

Components that do not apply to the request are left out and the remaining
weights renormalized (ADR-011). Keep this rule intact in refactors.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vsa.config import ObjectWeights
from vsa.expansion.query_expander import Concept, ConceptKind, ExpandedQuery
from vsa.features import ColumnFeatures
from vsa.models import ColumnHit, ObjectMatch
from vsa.scoring.combine import level_for
from vsa.scoring.rules import covers
from vsa.text.normalize import fold, stem

MAX_RELATED_COLUMNS = 8
# Extra columns beyond concept carriers must reach this share of the best score.
RELATED_MIN_SHARE = 0.6

# Folded column name -> suitability for a period-level (monthly…) request.
PERIOD_COLUMNS: dict[str, float] = {
    "period": 1.0,
    "datadate": 0.8,  # often month-end snapshots (§2b)
    "reportdate": 0.8,
    "kkbdate": 0.6,
    "trandate": 0.6,
    "trndate": 0.6,
    "transactiondate": 0.6,
    "transferdate": 0.6,
}
# ... and for a daily request.
DAILY_COLUMNS: dict[str, float] = {
    "datadate": 1.0,
    "trandate": 1.0,
    "trndate": 1.0,
    "transactiondate": 1.0,
    "transferdate": 1.0,
    "reportdate": 0.8,
    "kkbdate": 0.6,
    "period": 0.4,
}
CUSTOMER_KEYS = frozenset(
    {"customerpartyid", "customerid", "accountnumber", "customernumber", "partyid"}
)
_CUSTOMER_TOKEN = stem(fold("müşteri"))

# Long-format breakdown (Ek A.1/A.3): a dimension column such as ProductName or
# FINANCETYPE carries breakdown values as rows instead of separate columns.
DIMENSION_SUFFIXES = (
    "name", "type", "typename", "tip", "tipi", "tur", "turu", "code", "kod",
    "category", "kategori", "group", "grup", "class",
)  # fmt: skip
PRODUCT_HINTS = frozenset({stem(fold("ürün")), "product", "financetype", "producttype"})
# A dimension limited to one product family ("CardProductNumberName") cannot carry
# values from other families, so it does not qualify.
PRODUCT_FAMILY_TOKENS = frozenset({"card", "kart", "cc", "account", "hesab", "deposit"})


@dataclass(frozen=True, slots=True)
class ObjectColumns:
    """All dictionary columns of one object, for coverage/time/granularity checks."""

    key: str
    features: tuple[ColumnFeatures, ...]


def wants_customer_view(q: ExpandedQuery) -> bool:
    if _CUSTOMER_TOKEN in q.tokens:
        return True
    return any(fold(g.term).startswith("musteri") for g in q.term_groups)


def time_component(obj: ObjectColumns, concept: Concept) -> tuple[float, ColumnFeatures | None]:
    table = DAILY_COLUMNS if concept.value == "günlük" else PERIOD_COLUMNS
    best: tuple[float, ColumnFeatures | None] = (0.0, None)
    for f in obj.features:
        s = table.get(f.name_folded, 0.0)
        if s > best[0]:
            best = (s, f)
    return best


def product_dimension(obj: ObjectColumns) -> ColumnFeatures | None:
    """A general product-type dimension column of the object, if any (long format)."""
    for f in obj.features:
        if (
            f.name_folded.endswith(DIMENSION_SUFFIXES)
            and (f.name_tokens & PRODUCT_HINTS or f.name_folded in PRODUCT_HINTS)
            and not f.name_tokens & PRODUCT_FAMILY_TOKENS
        ):
            return f
    return None


def aggregate(
    hits: Mapping[int, ColumnHit],
    q: ExpandedQuery,
    objects: Mapping[str, ObjectColumns],
    weights: ObjectWeights,
    min_candidate_score: float,
) -> list[ObjectMatch]:
    """Group scored columns by object and rank objects. ``hits`` must hold a scored
    ColumnHit for every column of every candidate object."""
    content = q.content_concepts
    time_concept = q.time_concept
    customer = wants_customer_view(q)

    results: list[ObjectMatch] = []
    for key, obj in objects.items():
        obj_hits = [hits[f.col.id] for f in obj.features if f.col.id in hits]
        if not obj_hits:
            continue
        best = max(obj_hits, key=lambda h: (h.rule_score, h.raw_score))
        if best.rule_score <= 0:
            continue

        covered = [c for c in content if any(covers(f.all_tokens, c) for f in obj.features)]
        dimension: ColumnFeatures | None = None
        long_values: list[Concept] = []
        pending = [c for c in q.breakdown_values if c not in covered]
        if pending and (dimension := product_dimension(obj)) is not None:
            long_values = pending
            covered = [c for c in content if c in covered or c in long_values]
        components: dict[str, float] = {"best_column": best.rule_score}
        active: dict[str, float] = {"best_column": weights.best_column}
        if content:
            components["coverage"] = q.coverage(covered)
            active["coverage"] = weights.coverage
        time_col: ColumnFeatures | None = None
        if time_concept is not None:
            components["time"], time_col = time_component(obj, time_concept)
            active["time"] = weights.time
        if customer:
            has_key = any(f.name_folded in CUSTOMER_KEYS for f in obj.features)
            components["granularity"] = 1.0 if has_key else 0.5
            active["granularity"] = weights.granularity

        total_w = sum(active.values())
        score = sum(components[k] * w for k, w in active.items()) / total_w

        related = _related_columns(
            obj, hits, best, covered, time_col, min_candidate_score, dimension
        )
        first = obj.features[0].col
        groups = sorted({f.col.dataset_group for f in obj.features if f.col.dataset_group})
        results.append(
            ObjectMatch(
                object_key=key,
                database=first.database,
                schema=first.schema,
                object_name=first.object_name,
                dataset_groups=groups,
                score=score,
                level=level_for(score),
                columns=related,
                components=components,
                covered=[c.label for c in covered],
                missing=[c.label for c in content if c not in covered],
                long_format_values=[c.label for c in long_values],
                dimension_column=dimension.col.column if dimension else "",
            )
        )
    # Ties (several perfect matches clipped to 1.0) fall back to the unclipped best score.
    results.sort(key=lambda m: (-m.score, -m.columns[0].raw_score, m.object_key))
    return results


def _related_columns(
    obj: ObjectColumns,
    hits: Mapping[int, ColumnHit],
    best: ColumnHit,
    covered: Sequence[Concept],
    time_col: ColumnFeatures | None,
    min_candidate_score: float,
    dimension: ColumnFeatures | None = None,
) -> list[ColumnHit]:
    """Columns shown under "İlgili Alanlar": best match, one per covered concept,
    the time column, then other strong matches."""
    chosen: dict[int, ColumnHit] = {}

    def take(hit: ColumnHit, role: str) -> None:
        if hit.col.id not in chosen and len(chosen) < MAX_RELATED_COLUMNS:
            hit.role = hit.role or role
            chosen[hit.col.id] = hit

    take(best, "eşleşme")
    for concept in covered:
        if concept.kind is ConceptKind.MEASURE:
            continue
        carriers = [hits[f.col.id] for f in obj.features if covers(f.all_tokens, concept)]
        if carriers:
            take(max(carriers, key=lambda h: h.rule_score), "kavram")
    if dimension is not None:
        take(hits[dimension.col.id], "kırılım")
    if time_col is not None:
        take(hits[time_col.col.id], "zaman")
    for hit in sorted((hits[f.col.id] for f in obj.features), key=lambda h: -h.rule_score):
        if hit.rule_score >= max(min_candidate_score, RELATED_MIN_SHARE * best.rule_score):
            take(hit, "eşleşme")
    return list(chosen.values())
