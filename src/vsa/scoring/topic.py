"""Object-level topic fit (ADR-028).

Coverage asks "does the table mention every concept somewhere?". Wide tables — model
inputs, reports with 200 columns — mention almost everything, so coverage and the best
column saturate and stop telling tables apart. Topic fit asks instead "is this table
*about* the request?":

- sparse: each object is one BM25 document — its own name weighted highest, then its
  column names, synonyms and descriptions. BM25 length normalization is the point: a
  term in a 20-column table weighs more than the same term in a 200-column one.
- dense (when the vector index is on): similarity of the request to the table's own
  profile vector (name + column names + Turkish synonyms, see ``object_text``). The
  embedding model is multilingual, so "günlük kredi kartı işlemleri" meets
  "Daily Credit Card Transaction Pool" even though no word is shared. Without table
  vectors, the mean of the object's three most similar columns stands in.

Both parts are scaled to 0..1 across the candidates of the same request.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vsa.features import ColumnFeatures
from vsa.index.bm25 import BM25Index

# Object name ×4: "vCreditCardList" says more about the table than any one column.
OBJECT_FIELD_WEIGHTS: Mapping[str, float] = {
    "object": 4.0,
    "name": 1.0,
    "synonyms": 1.0,
    "description": 0.3,
}
DENSE_TOP_COLUMNS = 3
SPARSE_SHARE = 0.4  # the rest is the table vector's similarity


def build_topic_index(
    objects: Mapping[str, Sequence[ColumnFeatures]],
) -> tuple[list[str], BM25Index]:
    """One BM25 document per object; returns (object keys in doc order, index)."""
    keys = sorted(objects)
    docs = []
    for key in keys:
        feats = objects[key]
        docs.append(
            {
                "object": feats[0].object if feats else (),
                "name": [t for f in feats for t in f.name],
                "synonyms": [t for f in feats for t in f.synonym_tokens],
                "description": [t for f in feats for t in f.description],
            }
        )
    return keys, BM25Index.build(docs, OBJECT_FIELD_WEIGHTS)


def topic_scores(
    keys: Sequence[str],
    index: BM25Index,
    query_terms: Mapping[str, float],
    candidates: Sequence[str],
    objects: Mapping[str, Sequence[ColumnFeatures]],
    dense_sim: Mapping[int, float] | None = None,
    object_sim: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Topic fit 0..1 for each candidate object."""
    raw = {keys[d]: s for d, s in index.search(query_terms, top_k=len(keys))}
    wanted = set(candidates)
    sparse = {k: raw.get(k, 0.0) for k in wanted}
    top = max(sparse.values(), default=0.0)
    sparse = {k: v / top if top > 0 else 0.0 for k, v in sparse.items()}
    dense: dict[str, float] = {}
    if object_sim:
        dense = {k: object_sim.get(k, 0.0) for k in wanted}
    elif dense_sim:
        for k in wanted:
            sims = sorted((dense_sim.get(f.col.id, 0.0) for f in objects[k]), reverse=True)
            best = sims[:DENSE_TOP_COLUMNS]
            dense[k] = sum(best) / DENSE_TOP_COLUMNS if best else 0.0
    if not dense:
        return sparse
    lo, hi = min(dense.values()), max(dense.values())
    span = hi - lo
    return {
        k: SPARSE_SHARE * sparse[k]
        + (1 - SPARSE_SHARE) * ((dense[k] - lo) / span if span > 0 else 0.0)
        for k in wanted
    }
