"""Field-weighted BM25 over dictionary columns (HANDOVER §6.6).

Each field's term frequency is multiplied by its weight before the usual BM25
saturation, so a hit in the column name (weight 3) counts more than one in the
long, noisy description (weight 1). Pure Python — 11k documents need no library.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vsa.features import ColumnFeatures


def weighted_fields(f: ColumnFeatures) -> dict[str, Sequence[str]]:
    return {
        "name": f.name,
        "synonyms": f.synonym_tokens,
        "description": f.description,
        "object": f.object,
    }


@dataclass(slots=True)
class BM25Index:
    postings: dict[str, list[tuple[int, float]]]
    doc_len: list[float]
    avgdl: float
    k1: float = 1.2
    b: float = 0.75

    @property
    def n_docs(self) -> int:
        return len(self.doc_len)

    @classmethod
    def build(
        cls,
        docs: Sequence[Mapping[str, Sequence[str]]],
        weights: Mapping[str, float],
        k1: float = 1.2,
        b: float = 0.75,
    ) -> BM25Index:
        postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        doc_len: list[float] = []
        for doc_id, fields in enumerate(docs):
            tf: dict[str, float] = defaultdict(float)
            length = 0.0
            for field, tokens in fields.items():
                w = float(weights.get(field, 0.0))
                if w <= 0:
                    continue
                for tok in tokens:
                    tf[tok] += w
                length += w * len(tokens)
            for tok, freq in tf.items():
                postings[tok].append((doc_id, freq))
            doc_len.append(length)
        avgdl = sum(doc_len) / len(doc_len) if doc_len else 0.0
        return cls(dict(postings), doc_len, avgdl, k1, b)

    def idf(self, term: str) -> float:
        df = len(self.postings.get(term, ()))
        return math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))

    def search(self, query: Mapping[str, float], top_k: int) -> list[tuple[int, float]]:
        """Score documents for weighted query terms; returns (doc_id, score) best first."""
        scores: dict[int, float] = defaultdict(float)
        for term, q_weight in query.items():
            plist = self.postings.get(term)
            if not plist or q_weight <= 0:
                continue
            idf = self.idf(term)
            for doc_id, tf in plist:
                norm = 1 - self.b + self.b * self.doc_len[doc_id] / self.avgdl
                scores[doc_id] += q_weight * idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:top_k]

    def to_dict(self) -> dict[str, Any]:
        return {
            "k1": self.k1,
            "b": self.b,
            "avgdl": self.avgdl,
            "doc_len": self.doc_len,
            "postings": {t: [[d, f] for d, f in pl] for t, pl in self.postings.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BM25Index:
        postings = {t: [(int(d), float(f)) for d, f in pl] for t, pl in data["postings"].items()}
        return cls(
            postings=postings,
            doc_len=[float(x) for x in data["doc_len"]],
            avgdl=float(data["avgdl"]),
            k1=float(data["k1"]),
            b=float(data["b"]),
        )
