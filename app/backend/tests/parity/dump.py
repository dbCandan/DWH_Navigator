"""The shared dump rules of the parity test. Standard library only.

Every output is turned into plain data and written as canonical JSON: keys sorted, Turkish
letters unescaped, floats in Python's exact ``repr`` form (what ``json`` writes). Mappings
whose order carries meaning (query term weights, relevance, concept weights) are written as
ordered pairs. Objects are read by their dataclass fields, so the source's and the target's
classes dump the same way.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from enum import Enum
from typing import Any

MASK = "‹sebep›"
_SECONDS = re.compile(r"\(\d+ sn\)")


def plain(value: Any) -> Any:
    """Plain JSON data for any engine value."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {_key(k): plain(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((plain(v) for v in value), key=canonical)
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    raise TypeError(f"dökülemeyen değer: {type(value).__name__}")


def _key(key: Any) -> str:
    if isinstance(key, Enum):
        return str(key.value)
    if isinstance(key, (str, int, float, bool)) or key is None:
        return json.dumps(key, ensure_ascii=False) if not isinstance(key, str) else key
    return canonical(plain(key))


def canonical(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data: Any) -> str:
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def pairs(mapping: Mapping[Any, Any]) -> list[list[Any]]:
    """An ordered mapping as [key, value] pairs, keys dumped as data."""
    return [[plain(k), plain(v)] for k, v in mapping.items()]


# --------------------------------------------------------------------------- engine values


def expansion(q: Any) -> dict[str, Any]:
    """The expanded query with its concept weights and unknown concepts."""
    return {
        "text": q.text,
        "tokens": plain(q.tokens),
        "raw_words": plain(q.raw_words),
        "sparse_terms": pairs(q.sparse_terms),
        "concepts": plain(q.concepts),
        "term_groups": plain(q.term_groups),
        "expansion_terms": plain(q.expansion_terms),
        "expansion_tokens": plain(q.expansion_tokens),
        "synonym_hits": pairs(q.synonym_hits),
        "concept_weights": pairs(q.concept_weights),
        "unknown_concepts": plain(q.unknown_concepts),
    }


def hit(h: Any) -> dict[str, Any]:
    out = {f.name: plain(getattr(h, f.name)) for f in dataclasses.fields(h) if f.name != "col"}
    out["col"] = h.col.key
    return out


def match(m: Any) -> dict[str, Any]:
    out = {f.name: plain(getattr(m, f.name)) for f in dataclasses.fields(m)}
    out["columns"] = [hit(h) for h in m.columns]
    out["components"] = pairs(m.components)
    return out


def ranking(matches: Any) -> list[dict[str, Any]]:
    return [match(m) for m in matches]


def answer(encoded: Mapping[str, Any], *, mask_reason: str = "") -> dict[str, Any]:
    """An encoded AnalysisResult without the fields outside the comparison: the time it was
    written, its duration and the seconds in the method lines. ``mask_reason`` hides a reason
    text that question-analysis Requirement 5 changes on purpose."""
    data = {k: plain(v) for k, v in encoded.items() if k not in ("generated_at", "elapsed_ms")}
    data["method"] = [_SECONDS.sub("(# sn)", line) for line in data["method"]]
    return masked(data, mask_reason) if mask_reason else data


def masked(data: Any, reason: str) -> Any:
    if isinstance(data, str):
        return data.replace(reason, MASK)
    if isinstance(data, list):
        return [masked(v, reason) for v in data]
    if isinstance(data, dict):
        return {k: masked(v, reason) for k, v in data.items()}
    return data


def calls(recorded: Any) -> list[dict[str, Any]]:
    """The model calls: system and user messages, response schema and token limit."""
    return [
        {"system": c[0], "user": c[1], "schema": plain(c[2]), "max_tokens": c[3]} for c in recorded
    ]


# --------------------------------------------------------------------------- constants


def constant(value: Any) -> Any:
    """A module constant as data: patterns, translation tables, style objects included."""
    if isinstance(value, re.Pattern):
        return {"pattern": value.pattern, "flags": value.flags}
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: constant(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return [[constant(k), constant(v)] for k, v in value.items()]
    if isinstance(value, (set, frozenset)):
        return sorted((constant(v) for v in value), key=canonical)
    if isinstance(value, (list, tuple)):
        return [constant(v) for v in value]
    return {"repr": repr(value)}


def module_constants(module: Any) -> dict[str, Any]:
    """Every upper-case name of a module (functions and classes aside), and the members of the
    enumerations it defines."""
    out: dict[str, Any] = {}
    for name, value in sorted(vars(module).items()):
        if isinstance(value, type):
            if issubclass(value, Enum) and value.__module__ == module.__name__:
                out[f"enum:{name}"] = [[m.name, m.value] for m in value]
            continue
        if name.isupper() and not callable(value):
            out[name] = constant(value)
    return out
