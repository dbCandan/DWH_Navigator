"""M2 features: IDF-weighted coverage, breakdown values, product dimension. The evaluation
metrics belong to quality-evaluation."""

from __future__ import annotations

import pytest

from app.domain.analysis import DictColumn
from app.services.analysis.expansion.query_expander import (
    Concept,
    ConceptKind,
    QueryExpander,
)
from app.services.analysis.features import build_features
from app.services.analysis.scoring.aggregate import ObjectColumns, product_dimension
from app.services.analysis.text.normalize import load_stopwords

from .test_search import FEATURES, GROUPS, STOP

pytestmark = pytest.mark.unit


def test_weighted_coverage_prefers_rare_concepts() -> None:
    q = QueryExpander(GROUPS, FEATURES, STOP).expand("müşteri gayrimenkul")
    common, rare = q.content_concepts
    q.concept_weights = {common: 0.5, rare: 5.0}
    assert q.coverage([rare]) > 0.9
    assert q.coverage([common]) < 0.1
    assert q.coverage([]) == 0.0


def test_breakdown_values_from_parentheses() -> None:
    q = QueryExpander(GROUPS, FEATURES, STOP).expand(
        "aylık risk kırılımlı olarak (kredi kartı, ihtiyaç kredisi) gösteren"
    )
    values = {c.label for c in q.breakdown_values}
    assert values == {"kredi kartı", "ihtiyaç kredisi"}
    assert all(c.display().startswith("kırılım değeri:") for c in q.breakdown_values)


def test_no_breakdown_word_no_values() -> None:
    q = QueryExpander(GROUPS, FEATURES, STOP).expand("risk (kredi kartı, ihtiyaç kredisi)")
    assert q.breakdown_values == []


def _obj(*names: str) -> ObjectColumns:
    stop = load_stopwords([])
    feats = tuple(
        build_features(DictColumn(i, "DB", "S", "vX", n, "Ürün adı."), stop)
        for i, n in enumerate(names)
    )
    return ObjectColumns("DB.S.vX", feats)


def test_product_dimension_detection() -> None:
    dim = product_dimension(_obj("RiskAmountTL", "ProductName"))
    assert dim is not None and dim.col.column == "ProductName"
    kkb = product_dimension(_obj("FINANCETYPE"))
    assert kkb is not None
    # A single product family cannot carry other families' values.
    assert product_dimension(_obj("CardProductNumberName")) is None
    assert product_dimension(_obj("SegmentName")) is None


def test_concept_is_hashable_for_weights() -> None:
    c = Concept(ConceptKind.TERM, "risk", (("risk",),))
    assert {c: 1.0}[Concept(ConceptKind.TERM, "risk", (("risk",),))] == 1.0
