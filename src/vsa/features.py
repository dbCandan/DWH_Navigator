"""Pre-tokenized text features of dictionary columns, shared by search and scoring."""

from __future__ import annotations

from dataclasses import dataclass

from vsa.models import DictColumn
from vsa.text.normalize import fold, tokenize


@dataclass(frozen=True, slots=True)
class ColumnFeatures:
    col: DictColumn
    name_folded: str  # "cardlimitfullnesstoday" — for exact-name match
    name: tuple[str, ...]  # stemmed name parts (+ compound form)
    synonyms: tuple[tuple[str, ...], ...]  # each synonym phrase as a token tuple
    description: tuple[str, ...]  # stemmed description tokens, in order
    object: tuple[str, ...]  # stemmed object-name parts
    all_tokens: frozenset[str]  # name ∪ synonyms ∪ description — for concept checks
    name_tokens: frozenset[str]

    @property
    def synonym_tokens(self) -> list[str]:
        return [t for phrase in self.synonyms for t in phrase]


def build_features(col: DictColumn, stopwords: frozenset[str]) -> ColumnFeatures:
    name = tuple(tokenize(col.column, stopwords=stopwords))
    synonyms = tuple(
        phrase
        for s in col.synonyms
        if (phrase := tuple(tokenize(s, stopwords=stopwords, keep_compound=False)))
    )
    description = tuple(tokenize(col.description, stopwords=stopwords, keep_compound=False))
    obj = tuple(tokenize(col.object_name, stopwords=stopwords))
    syn_flat = {t for p in synonyms for t in p}
    return ColumnFeatures(
        col=col,
        name_folded=fold(col.column),
        name=name,
        synonyms=synonyms,
        description=description,
        object=obj,
        all_tokens=frozenset(name) | syn_flat | frozenset(description),
        name_tokens=frozenset(name),
    )


def contains_sequence(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    """True if ``needle`` occurs as a contiguous run inside ``haystack``."""
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    first = needle[0]
    return any(
        haystack[i] == first and haystack[i : i + n] == needle for i in range(len(haystack) - n + 1)
    )
