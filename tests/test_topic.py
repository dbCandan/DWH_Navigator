"""Object-level topic fit (ADR-028)."""

from __future__ import annotations

from vsa.config import FlagPenalty, ObjectWeights
from vsa.expansion.query_expander import QueryExpander
from vsa.models import ColumnHit
from vsa.scoring.aggregate import aggregate
from vsa.scoring.rules import score_column
from vsa.scoring.topic import build_topic_index, topic_scores

from .test_aggregate import STOP, build
from .test_search import GROUPS

# A wide model-input table that mentions cards in passing, and the table that is
# actually about card transactions. Column-level signals cannot tell them apart.
TABLES = {
    "vChurnModelInput": [
        ("CustomerPartyId", "Müşteri anahtarı."),
        ("CardTransactionCount", "Kart işlem adedi."),
        *[(f"Feature{i}", f"Model girdisi {i}.") for i in range(40)],
    ],
    "vCardTransaction": [
        ("CustomerPartyId", "Müşteri anahtarı."),
        ("CardTransactionAmount", "Kart işlem tutarı."),
        ("CardTransactionDate", "Kart işlem tarihi."),
    ],
}


def _topic(query: str, object_sim: dict[str, float] | None = None) -> dict[str, float]:
    _, objects = build(TABLES)
    feats = {k: o.features for k, o in objects.items()}
    keys, index = build_topic_index(feats)
    q = QueryExpander(GROUPS, [f for o in objects.values() for f in o.features], STOP).expand(query)
    return topic_scores(keys, index, q.sparse_terms, sorted(feats), feats, None, object_sim)


def test_topic_prefers_the_table_about_the_request() -> None:
    """BM25 over whole tables: the object name counts most, width is penalized."""
    t = _topic("kart işlem")
    assert t["DB.S.vCardTransaction"] == 1.0
    assert t["DB.S.vChurnModelInput"] < 0.6


def test_table_vector_joins_the_score() -> None:
    """The table profile vector bridges Turkish requests and English names."""
    t = _topic("kart işlem", {"DB.S.vCardTransaction": 0.2, "DB.S.vChurnModelInput": 0.6})
    plain = _topic("kart işlem")
    assert t["DB.S.vChurnModelInput"] > plain["DB.S.vChurnModelInput"]
    assert t["DB.S.vCardTransaction"] < plain["DB.S.vCardTransaction"]


def test_topic_breaks_the_tie_between_wide_and_focused_tables() -> None:
    _, objects = build(TABLES)
    feats = [f for o in objects.values() for f in o.features]
    q = QueryExpander(GROUPS, feats, STOP).expand("kart işlem")
    hits: dict[int, ColumnHit] = {
        f.col.id: score_column(f, 1.0, 1.0, q, FlagPenalty()) for f in feats
    }
    by_obj = {k: o.features for k, o in objects.items()}
    keys, index = build_topic_index(by_obj)
    topic = topic_scores(keys, index, q.sparse_terms, sorted(by_obj), by_obj)
    ranked = aggregate(hits, q, objects, ObjectWeights(), 0.25, topic)
    assert ranked[0].object_name == "vCardTransaction"
    assert "topic" in ranked[0].components
    # Without the component (weight 0) the rule falls back to the old signals only.
    off = aggregate(hits, q, objects, ObjectWeights(topic=0.0), 0.25, topic)
    assert all("topic" not in m.components for m in off)
