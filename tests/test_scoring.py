"""Column rule score (HANDOVER §9.2) — every rule has a test."""

from __future__ import annotations

from vsa.expansion.query_expander import QueryExpander
from vsa.features import build_features
from vsa.models import DictColumn, Level
from vsa.scoring.combine import level_for
from vsa.scoring.rules import (
    CAVEAT_DERIVATION,
    CAVEAT_PII,
    score_column,
)
from vsa.text.normalize import load_stopwords

from .test_search import GROUPS

STOP = load_stopwords(["ve", "bazlı", "nerede"])


def make(name: str, desc: str, syn: tuple[str, ...] = (), **kw: object) -> DictColumn:
    return DictColumn(0, "DB", "S", "vObj", name, desc, synonyms=syn, **kw)  # type: ignore[arg-type]


def score(c: DictColumn, query: str, bm25: float = 5.0, max_bm25: float = 10.0) -> tuple:  # type: ignore[type-arg]
    f = build_features(c, STOP)
    q = QueryExpander(GROUPS, [f], STOP).expand(query)
    return score_column(f, bm25, max_bm25, q), q


BASE = make("Foo", "Kart limiti.")


def test_exact_name_bonus() -> None:
    exact, _ = score(make("CreditCardLimitRate", "Kart limiti."), "CreditCardLimitRate")
    other, _ = score(make("CreditCardLimitRatio", "Kart limiti."), "CreditCardLimitRate")
    assert exact.raw_score > other.raw_score
    assert any("birebir" in s for s in exact.signals)


def test_name_covers_concepts() -> None:
    h, _ = score(make("CardLimitFullness", "x"), "kart limit doluluk oranı")
    assert any("Kolon adı talep kavramlarını" in s for s in h.signals)


def test_description_phrase_bonus() -> None:
    with_phrase, _ = score(make("Foo", "Kart limit doluluk oranıdır."), "doluluk oranı kart")
    without, _ = score(make("Foo", "Kart oranı ve doluluk."), "doluluk oranı kart")
    assert with_phrase.raw_score > without.raw_score


def test_synonym_bonus() -> None:
    syn, _ = score(make("Foo", "Kart.", ("limit doluluk",)), "limit doluluk")
    plain, _ = score(make("Foo", "Kart.", ("başka",)), "limit doluluk")
    assert syn.raw_score - plain.raw_score >= 0.14
    assert any("eş anlamlılar" in s for s in syn.signals)


def test_derivation_penalty_when_ratio_missing() -> None:
    ready, _ = score(make("CardLimitRate", "Kart limit oranı."), "kart limit oranı")
    parts, _ = score(make("CardLimit", "Kart limit tutarı."), "kart limit oranı")
    assert CAVEAT_DERIVATION in parts.caveats
    assert CAVEAT_DERIVATION not in ready.caveats


def test_scope_negation_penalty() -> None:
    """HANDOVER Ek A.2: TotalLimitFullness is "kart bazlı değil"."""
    neg, _ = score(make("TotalLimitFullness", "Toplam limit. Kart bazlı değil."), "kart limit")
    pos, _ = score(make("TotalLimitFullness", "Toplam limit. Kart bazlıdır."), "kart limit")
    assert neg.raw_score < pos.raw_score
    assert any("Kapsam farkı" in c for c in neg.caveats)


def test_pii_caveat() -> None:
    h, _ = score(make("CustomerName", "Ad soyad; KVKK kapsamında.", has_pii=True), "müşteri adı")
    assert CAVEAT_PII in h.caveats


def test_score_clipped() -> None:
    h, _ = score(
        make("CardLimitFullness", "Kart limit doluluk oranı.", ("limit doluluk",)),
        "CardLimitFullness limit doluluk oranı kart",
        bm25=10,
    )
    assert h.rule_score == 1.0
    assert h.raw_score > 1.0


def test_levels() -> None:
    assert level_for(0.80) is Level.HIGH
    assert level_for(0.79) is Level.MEDIUM
    assert level_for(0.50) is Level.MEDIUM
    assert level_for(0.49) is Level.LOW


def test_level_matches_displayed_percent() -> None:
    assert level_for(0.797) is Level.HIGH  # shown as %80
    assert level_for(0.794) is Level.MEDIUM  # shown as %79
    assert level_for(0.496) is Level.MEDIUM  # shown as %50
