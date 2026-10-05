"""Object-level topic fit (ADR-028).

Coverage asks "does the table mention every concept somewhere?". Wide tables — model
inputs, reports with 200 columns — mention almost everything, so coverage and the best
column saturate and stop telling tables apart. Topic fit asks instead "is this table
*about* the request?":

each object is one BM25 document — its own name weighted highest, then its profile (the
object sheet's description and grain, ADR-040), its column names, synonyms and
descriptions. BM25 length normalization is the point: a term in a
20-column table weighs more than the same term in a 200-column one. Scores are scaled
to 0..1 across the candidates of the same request.
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
    # ×3 measured on the 83 answerable reference questions: acceptable table in the top 5
    # 0.84 -> 0.89, MRR of the primary table 0.40 -> 0.45 (column summaries did not help).
    "profile": 3.0,
}


def build_topic_index(
    objects: Mapping[str, Sequence[ColumnFeatures]],
    profiles: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[str], BM25Index]:
    """One BM25 document per object; returns (object keys in doc order, index).
    ``profiles``: tokenized object description + grain per object key."""
    keys = sorted(objects)
    profiles = profiles or {}
    docs = []
    for key in keys:
        feats = objects[key]
        docs.append(
            {
                "object": feats[0].object if feats else (),
                "name": [t for f in feats for t in f.name],
                "synonyms": [t for f in feats for t in f.synonym_tokens],
                "description": [t for f in feats for t in f.description],
                "profile": list(profiles.get(key, ())),
            }
        )
    return keys, BM25Index.build(docs, OBJECT_FIELD_WEIGHTS)


def topic_scores(
    keys: Sequence[str],
    index: BM25Index,
    query_terms: Mapping[str, float],
    candidates: Sequence[str],
) -> dict[str, float]:
    """Topic fit 0..1 for each candidate object."""
    raw = {keys[d]: s for d, s in index.search(query_terms, top_k=len(keys))}
    wanted = set(candidates)
    sparse = {k: raw.get(k, 0.0) for k in wanted}
    top = max(sparse.values(), default=0.0)
    return {k: v / top if top > 0 else 0.0 for k, v in sparse.items()}
