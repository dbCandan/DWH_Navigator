"""Deterministic column-level rule score (HANDOVER §9.2, ADR-010, ADR-012).

    base  = 0.35 × search + 0.25 × column_concept_coverage (IDF-weighted)
    search = relative BM25, or with the hybrid index (M3)
             (1 − w) × relative BM25 + w × normalized dense similarity
    score = (base + bonuses − penalties) × flag multipliers, clipped to [0, 1]

Time and granularity are NOT scored here — they are object properties (ADR-010).
"""

from __future__ import annotations

from vsa.config import FlagPenalty
from vsa.expansion.query_expander import Concept, ConceptKind, ExpandedQuery
from vsa.features import ColumnFeatures, contains_sequence
from vsa.models import ColumnHit, FlagKind

W_BASE_RELATIVE = 0.35
W_BASE_COVERAGE = 0.25
BONUS_EXACT_NAME = 0.30
BONUS_NAME_COVERS = 0.20
BONUS_DESCRIPTION_PHRASE = 0.15
BONUS_SYNONYM = 0.15
BONUS_TERM_DICTIONARY = 0.10
PENALTY_DERIVATION = 0.15
PENALTY_SCOPE = 0.10
DENSE_SIGNAL_MIN = 0.85  # normalized dense similarity worth mentioning in the reason
NEGATION_WINDOW = 1  # "bazlı" is a stopword, so "Kart bazlı değil" -> (kart, değil)

CAVEAT_MODEL_ESTIMATED = "Açıklama model tahmini; iş birimiyle doğrulanmalı"
CAVEAT_NAMING_MISMATCH = "Kalite bulgusu: kolon adı ile içerik uyumsuz"
CAVEAT_DERIVATION = "Hazır oran değil; oran pay/payda alanlarından türetilmeli"
CAVEAT_PII = "Kişisel veri (KVKK) içerir; maskelenmiş alternatif tercih edilmeli"


def covers(tokens: frozenset[str], concept: Concept) -> bool:
    """A token set satisfies a concept if it holds every token of some alternative."""
    return any(alt and set(alt) <= tokens for alt in concept.alternatives)


def score_column(
    f: ColumnFeatures,
    bm25: float,
    max_bm25: float,
    q: ExpandedQuery,
    penalty: FlagPenalty,
    dense: float | None = None,
    dense_weight: float = 0.0,
) -> ColumnHit:
    """``dense`` is the column's normalized (0–1) semantic similarity to the query when
    the hybrid index is on (M3); it takes ``dense_weight`` of the search component."""
    content = q.content_concepts
    covered = [c for c in content if covers(f.all_tokens, c)]
    relative = bm25 / max_bm25 if max_bm25 > 0 else 0.0
    if dense is not None and dense_weight > 0:
        relative = (1 - dense_weight) * relative + dense_weight * dense
    coverage = q.coverage(covered)
    score = W_BASE_RELATIVE * relative + W_BASE_COVERAGE * coverage

    signals: list[str] = []
    caveats: list[str] = []

    if f.name_folded in q.raw_words:
        score += BONUS_EXACT_NAME
        signals.append("Kolon adı talepteki ifadeyle birebir aynı")

    in_name = [c for c in covered if c.kind is ConceptKind.TERM and covers(f.name_tokens, c)]
    if len(in_name) >= 2 or (in_name and len(content) == 1):
        score += BONUS_NAME_COVERS
        signals.append(
            "Kolon adı talep kavramlarını taşıyor: " + ", ".join(c.label for c in in_name)
        )

    phrase = _description_phrase(f, covered)
    if phrase:
        score += BONUS_DESCRIPTION_PHRASE
        signals.append(f"Sözlük açıklamasında “{phrase}” ifadesi geçiyor")

    syn = q.synonym_hits.get(f.col.id)
    if syn:
        score += BONUS_SYNONYM
        signals.append("Sözlüğün eş anlamlılar listesinde: " + ", ".join(f"“{s}”" for s in syn))

    via_terms = sorted(q.expansion_tokens & f.all_tokens)
    if via_terms and q.term_groups:
        score += BONUS_TERM_DICTIONARY
        signals.append("Kurumsal terim sözlüğü üzerinden eşleşti")

    needs_derivation = False
    if q.measure == "oran" and covered:
        ratio = next(c for c in content if c.kind is ConceptKind.MEASURE)
        if not covers(f.name_tokens | frozenset(f.description), ratio):
            needs_derivation = True
            score -= PENALTY_DERIVATION
            caveats.append(CAVEAT_DERIVATION)

    # Last, so the reason text leads with the concrete (lexical) evidence.
    if dense is not None and dense >= DENSE_SIGNAL_MIN:
        signals.append(f"Anlamsal benzerlik yüksek (%{round(dense * 100)})")

    negated = _negated_concepts(f, covered)
    if negated:
        score -= PENALTY_SCOPE
        for c in negated:
            caveats.append(f"Kapsam farkı: açıklamaya göre “{c.label}” bazlı değil")

    for c in covered:
        if c.scope_note:
            caveats.append(c.scope_note)

    if f.col.has_flag(FlagKind.MODEL_ESTIMATED):
        score *= penalty.model_estimated
        caveats.append(CAVEAT_MODEL_ESTIMATED)
    if f.col.has_flag(FlagKind.NAMING_MISMATCH):
        score *= penalty.naming_mismatch
        caveats.append(CAVEAT_NAMING_MISMATCH)
    for flag in f.col.flags:
        if flag.kind is FlagKind.NEEDS_VERIFICATION:
            caveats.append(flag.text)
    if f.col.has_pii:
        caveats.append(CAVEAT_PII)

    return ColumnHit(
        col=f.col,
        search_score=bm25,
        rule_score=max(0.0, min(1.0, score)),
        raw_score=score,
        signals=signals,
        caveats=caveats,
        concepts=[c.label for c in covered],
        needs_derivation=needs_derivation,
    )


def _negated_concepts(f: ColumnFeatures, covered: list[Concept]) -> list[Concept]:
    """Concepts the description explicitly rules out: "Kart bazlı değil, …" (§9.2
    "kapsam farkı"). A concept token within a few words before "değil" counts."""
    out: list[Concept] = []
    desc = f.description
    for i, tok in enumerate(desc):
        if not tok.startswith("degil"):
            continue
        window = frozenset(desc[max(0, i - NEGATION_WINDOW) : i])
        for c in covered:
            if c.kind is ConceptKind.TERM and c not in out and covers(window, c):
                out.append(c)
    return out


def _description_phrase(f: ColumnFeatures, covered: list[Concept]) -> str | None:
    """First multi-word concept alternative found verbatim in the description."""
    for c in covered:
        for alt in c.alternatives:
            if len(alt) >= 2 and contains_sequence(f.description, alt):
                return c.label
    return None
