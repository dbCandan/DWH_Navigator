"""Answers worth keeping (ADR-035): keys, fingerprint and the JSON form of a result.

An analyst answer takes minutes; the same question asked again — or a question that
says the same thing in other words — gets the earlier answer back. Two keys find it:

* ``text_key``: the question's words, folded (case, Turkish letters, punctuation and
  spacing do not matter);
* ``meaning_key``: the set of concepts the rule engine reads in the question. Members of
  one term-dictionary group are one concept ("müşteri no" = "hesap no", ADR-009), word
  order and stopwords do not count, numbers and negations do.

An answer is only reused under the same ``fingerprint``: dictionary version, chat
model, term dictionary and every setting that shapes an answer. Pure module;
the file store lives in ``vsa.web.answer_store``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, fields
from typing import Any

from vsa.config import Settings
from vsa.expansion.query_expander import ExpandedQuery
from vsa.llm import analyst_prompts
from vsa.models import (
    AnalysisResult,
    ColumnHit,
    DictColumn,
    Level,
    Note,
    ObjectMatch,
    TermGroup,
    Verdict,
)
from vsa.text.normalize import fold

CACHE_FORMAT = 2  # bump when the stored form or the answer's meaning changes (2: `missing`)
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
# Words that turn a request around; they are stopwords or vanish in stemming, so the
# meaning key carries them explicitly ("kartı olan" ≠ "kartı olmayan").
NEGATIONS = frozenset({"yok", "degil", "haric", "harici", "disinda", "olmayan", "olmadan",
                       "olmayanlar", "hic", "without", "except", "not", "no"})  # fmt: skip
# Settings that do not change an answer: where files go, and this feature's own switches.
_NEUTRAL = ("report", "cache", "index")
_LLM_KEYS = ("model", "temperature", "reasoning_effort", "seed")


def text_key(query: str) -> str:
    """The question's words, folded and single-spaced."""
    return " ".join(_WORD.findall(fold(query)))


def meaning_key(q: ExpandedQuery) -> str:
    """Canonical concept set of a question; "" when it has no content concept (too
    little to call two questions the same)."""
    if not q.content_concepts:
        return ""
    parts = set()
    for c in q.concepts:
        # Alternatives, not the label: every member of a term group shares them.
        alts = ",".join(sorted("+".join(a) for a in c.alternatives))
        parts.add(f"{c.kind.value}:{c.value}:{alts}:{int(c.breakdown_value)}")
    words = set(_WORD.findall(fold(q.text)))
    parts.update(f"sayı:{w}" for w in words if w.isdigit())
    parts.update(f"olumsuz:{w}" for w in words & NEGATIONS)
    return "|".join(sorted(parts))


def prompts_digest() -> str:
    """The analyst's instructions and output schemas: a prompt change changes the answer,
    so answers written under an older prompt are not given again."""
    parts = [v for k, v in sorted(vars(analyst_prompts).items())
             if k.isupper() and isinstance(v, (str, dict))]  # fmt: skip
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def fingerprint(
    settings: Settings,
    dictionary_version: str,
    term_groups: list[TermGroup],
    top_n: int,
) -> str:
    """What an answer depends on besides the question; any change makes old answers
    unusable (they stay on disk until cleared)."""
    raw = asdict(settings)
    for key in _NEUTRAL:
        raw.pop(key, None)
    raw["llm"] = {k: raw["llm"][k] for k in _LLM_KEYS}
    raw["_"] = {
        "format": CACHE_FORMAT,
        "dictionary": dictionary_version,
        "terms": [[g.term, *g.equivalents, g.domain, g.note] for g in term_groups],
        "top": top_n,
        "prompts": prompts_digest(),
    }
    blob = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- JSON form


def _hit_to_dict(h: ColumnHit) -> dict[str, Any]:
    d = {f.name: getattr(h, f.name) for f in fields(h) if f.name != "col"}
    d["col"] = h.col.key
    return d


def _match_to_dict(m: ObjectMatch) -> dict[str, Any]:
    d = {f.name: getattr(m, f.name) for f in fields(m) if f.name != "columns"}
    d["level"] = m.level.value
    d["columns"] = [_hit_to_dict(h) for h in m.columns]
    return d


def encode(r: AnalysisResult) -> dict[str, Any]:
    """An answer as JSON-ready data; columns by key (the dictionary holds the rest)."""
    d = {f.name: getattr(r, f.name) for f in fields(r)}
    d["verdict"] = r.verdict.value
    d["objects"] = [_match_to_dict(m) for m in r.objects]
    d["near_misses"] = [_match_to_dict(m) for m in r.near_misses]
    d["notes"] = [asdict(n) for n in r.notes]
    return d


def _match_from_dict(d: dict[str, Any], columns: dict[str, DictColumn]) -> ObjectMatch:
    hits = []
    for h in d["columns"]:
        col = columns[h["col"]]  # KeyError: not in this dictionary -> unusable answer
        hits.append(ColumnHit(**{**h, "col": col}))
    return ObjectMatch(**{**d, "level": Level(d["level"]), "columns": hits})


def decode(d: dict[str, Any], columns: dict[str, DictColumn]) -> AnalysisResult | None:
    """The answer back, every column resolved in the current dictionary; None when the
    stored form no longer fits (an older format, a column that is gone)."""
    try:
        return AnalysisResult(
            **{
                **d,
                "verdict": Verdict(d["verdict"]),
                "objects": [_match_from_dict(m, columns) for m in d["objects"]],
                "near_misses": [_match_from_dict(m, columns) for m in d["near_misses"]],
                "notes": [Note(**n) for n in d["notes"]],
            }
        )
    except (KeyError, TypeError, ValueError):
        return None
