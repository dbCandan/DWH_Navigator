"""BM25 index, query expansion and concept extraction."""

from __future__ import annotations

from vsa.expansion.query_expander import ConceptKind, QueryExpander
from vsa.features import build_features, contains_sequence
from vsa.index.bm25 import BM25Index, weighted_fields
from vsa.models import DictColumn, TermGroup
from vsa.text.normalize import load_stopwords

STOP = load_stopwords(["ve", "bilgisi", "verisi", "var", "nerede", "ihtiyacımız", "bazında"])

GROUPS = [
    TermGroup("kredi kartı", ("KK", "credit card", "kart")),
    TermGroup("limit", ("tanımlı limit", "card limit")),
    TermGroup("tahsis", ("limit", "allotment")),
    TermGroup("doluluk oranı", ("kullanım oranı", "fullness", "limit doluluk")),
    TermGroup("ihtiyaç kredisi", ("tüketici kredisi", "consumer loan")),
    TermGroup("fon kullandırım", ("kredi", "loan")),
    TermGroup("veri tarihi", ("data date",)),
    TermGroup("tutar", ("amount",), domain="finansal"),
]


def col(i: int, name: str, desc: str, syn: tuple[str, ...] = (), obj: str = "vObj") -> DictColumn:
    return DictColumn(i, "DB", "S", obj, name, desc, synonyms=syn)


COLUMNS = [
    col(0, "CardLimitFullnessToday", "Kartın bugünkü limit doluluk oranıdır.", ("limit doluluk",)),
    col(1, "CustomerPartyId", "Müşterinin DWH anahtarıdır.", ("müşteri SKEY",)),
    col(2, "ConsumerBalance", "Tüketici kredisi bakiyesidir.", ("tüketici finansmanı bakiyesi",)),
    col(3, "BirthDate", "Müşterinin doğum tarihidir.", ("doğum tarihi",)),
]
FEATURES = [build_features(c, STOP) for c in COLUMNS]


def expander() -> QueryExpander:
    return QueryExpander(GROUPS, FEATURES, STOP)


class TestBM25:
    def test_name_field_outweighs_description(self) -> None:
        docs = [
            {"name": ["limit"], "description": ["x", "y"]},
            {"name": ["x"], "description": ["limit", "y"]},
        ]
        idx = BM25Index.build(docs, {"name": 3, "description": 1})
        ranked = idx.search({"limit": 1.0}, top_k=2)
        assert [d for d, _ in ranked] == [0, 1]
        assert ranked[0][1] > ranked[1][1]

    def test_query_weight_scales_score(self) -> None:
        idx = BM25Index.build([weighted_fields(f) for f in FEATURES], {"name": 3, "description": 1})
        full = dict(idx.search({"limit": 1.0}, 10))
        low = dict(idx.search({"limit": 0.6}, 10))
        assert low[0] < full[0]

    def test_roundtrip(self) -> None:
        idx = BM25Index.build([weighted_fields(f) for f in FEATURES], {"name": 3, "synonyms": 2})
        again = BM25Index.from_dict(idx.to_dict())
        q = {"limit": 1.0, "dolul": 1.0}
        assert again.search(q, 5) == idx.search(q, 5)


class TestExpansion:
    def test_longest_phrase_wins(self) -> None:
        q = expander().expand("ihtiyaç kredisi")
        assert [g.term for g in q.term_groups] == ["ihtiyaç kredisi"]  # not "fon kullandırım"

    def test_head_term_preferred_on_tie(self) -> None:
        q = expander().expand("limit")
        assert [g.term for g in q.term_groups] == ["limit"]  # not "tahsis"

    def test_bidirectional(self) -> None:
        q = expander().expand("fullness")
        assert q.term_groups[0].term == "doluluk oranı"
        assert "kullanım oranı" in q.expansion_terms

    def test_expansion_weight_only_on_new_terms(self) -> None:
        q = expander().expand("kredi kartı")
        assert q.sparse_terms["kart"] == 1.0
        assert q.sparse_terms["credit"] == 0.6
        assert q.text == "kredi kartı"  # ADR-004: the original wording is kept

    def test_stopword_in_term_phrase_does_not_fire(self) -> None:
        """ "veri tarihi" must not shrink to "tarih" and match "doğum tarihi"."""
        q = expander().expand("müşterinin doğum tarihi")
        assert all(g.term != "veri tarihi" for g in q.term_groups)

    def test_synonym_hits(self) -> None:
        q = expander().expand("limit doluluk nerede")
        assert q.synonym_hits == {0: ["limit doluluk"]}

    def test_disabled_expansion(self) -> None:
        e = QueryExpander(GROUPS, FEATURES, STOP, enabled=False)
        q = e.expand("kredi kartı")
        assert q.expansion_tokens == frozenset()


class TestConcepts:
    def test_time_and_breakdown_request(self) -> None:
        """A request with a time and a breakdown word."""
        q = expander().expand(
            "Müşterilerin risk bilgilerini aylık bazda ve kırılımlı olarak "
            "(kredi kartı, gayrimenkul, ihtiyaç kredisi) gösteren tablo"
        )
        kinds = {c.kind for c in q.concepts}
        assert {ConceptKind.TIME, ConceptKind.BREAKDOWN, ConceptKind.TERM} <= kinds
        assert q.time_concept is not None and q.time_concept.value == "aylık"
        labels = {c.label for c in q.content_concepts}
        assert {"kredi kartı", "ihtiyaç kredisi", "risk", "gayrimenkul"} <= labels
        assert "aylık" not in labels and "kırılımlı" not in labels

    def test_measure_concept(self) -> None:
        q = expander().expand("limit doluluk oranı")
        assert q.measure == "oran"

    def test_finance_domain_is_measure_not_term(self) -> None:
        q = expander().expand("transfer tutarı")
        assert q.measure == "tutar"
        assert all(c.label != "tutar" for c in q.concepts if c.kind is ConceptKind.TERM)

    def test_labels_use_surface_form(self) -> None:
        q = expander().expand("müşteri riski")
        assert {c.label for c in q.content_concepts} == {"müşteri", "riski"}


def test_contains_sequence() -> None:
    assert contains_sequence(("a", "b", "c"), ("b", "c"))
    assert not contains_sequence(("a", "b", "c"), ("c", "b"))
    assert not contains_sequence(("a",), ())
