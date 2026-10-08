"""The term dictionary and the stopwords (data-dictionary/PRDs/002-vocabulary-management).

Both lists change only as a whole. A saved or imported list passes the source's checks
(``check_terms`` / ``check_stopwords`` of ``76e21a3``) with the new length limits of Requirement
3 and 4; the first failure is reported in the source's Turkish text, built only from what the
administrator sent. Equal terms and equal stopwords are decided by the application's Turkish
folding helper alone.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from app.domain.turkish_text import fold


class VocabularyList(StrEnum):
    TERMS = "terms"
    STOPWORDS = "stopwords"


class VocabularySource(StrEnum):
    """Where the last change of a list came from (Requirement 1)."""

    SEED = "baslangic"
    SCREEN = "ekran"
    EXCEL = "excel"


MAX_LIST_ITEMS = 5000
# Requirement 3 and 4 (new, Decision 7).
MAX_TERM_LENGTH = 200
MAX_EQUIVALENT_LENGTH = 200
MAX_DOMAIN_LENGTH = 100
MAX_NOTE_LENGTH = 1000
MAX_EQUIVALENTS = 100
MAX_STOPWORD_LENGTH = 100
MAX_GROUP_LENGTH = 200

TERM_FIELDS = ("term", "equivalents", "domain", "note")
STOPWORD_FIELDS = ("word", "group")

TermItem = dict[str, Any]
StopwordItem = dict[str, str]


class VocabularyRejected(ValueError):
    """A list breaks a rule: a stable code and the source's Turkish message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class VocabularyShapeError(ValueError):
    """A field of an item has the wrong JSON type; ``location`` names it, never its value."""

    def __init__(self, location: str) -> None:
        super().__init__(location)
        self.location = location


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _items(items: object) -> list[Mapping[str, Any]]:
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise VocabularyRejected("vocabulary_items_invalid", "Liste bekleniyordu")
    if len(items) > MAX_LIST_ITEMS:
        raise VocabularyRejected("vocabulary_too_many_items", f"En fazla {MAX_LIST_ITEMS} kayıt")
    return items


def _check_shape(items: Sequence[Mapping[str, Any]], kind: VocabularyList) -> None:
    """Requirement 3: field types are strict; a missing ``domain``/``note``/``group`` is ''."""

    fields = TERM_FIELDS if kind is VocabularyList.TERMS else STOPWORD_FIELDS
    for index, item in enumerate(items):
        for key, value in item.items():
            location = f"items.{index}.{key}" if key in fields else f"items.{index}"
            if key not in fields:
                raise VocabularyShapeError(location)
            if key == "equivalents":
                if not isinstance(value, list) or not all(isinstance(e, str) for e in value):
                    raise VocabularyShapeError(location)
            elif not isinstance(value, str):
                raise VocabularyShapeError(location)


def _too_long(message: str) -> VocabularyRejected:
    return VocabularyRejected("vocabulary_value_too_long", message)


def check_terms(items: object) -> list[TermItem]:
    """Clean term groups; an empty term, a group without equivalents or a term given
    twice (Turkish case-folded) is an error naming the row (the source's ``check_terms``).
    """

    rows = _items(items)
    _check_shape(rows, VocabularyList.TERMS)
    out: list[TermItem] = []
    seen: dict[str, int] = {}
    for n, rec in enumerate(rows, 1):
        term = _text(rec.get("term"))
        raw = rec.get("equivalents")
        equivalents = list(
            dict.fromkeys(e for e in map(_text, raw if isinstance(raw, list) else []) if e)
        )
        domain = _text(rec.get("domain"))
        note = _text(rec.get("note"))
        if not term:
            raise VocabularyRejected("vocabulary_term_empty", f"Satır {n}: terim boş")
        if len(term) > MAX_TERM_LENGTH:
            raise _too_long(f"Satır {n}: terim en fazla {MAX_TERM_LENGTH} karakter olabilir")
        if not equivalents:
            raise VocabularyRejected(
                "vocabulary_term_without_equivalents",
                f"“{term}”: en az bir eşdeğer gerekli",
            )
        if len(equivalents) > MAX_EQUIVALENTS:
            raise VocabularyRejected(
                "vocabulary_too_many_equivalents",
                f"“{term}”: en fazla {MAX_EQUIVALENTS} eşdeğer olabilir",
            )
        if any(len(e) > MAX_EQUIVALENT_LENGTH for e in equivalents):
            raise _too_long(f"“{term}”: eşdeğer en fazla {MAX_EQUIVALENT_LENGTH} karakter olabilir")
        if len(domain) > MAX_DOMAIN_LENGTH:
            raise _too_long(f"“{term}”: alan en fazla {MAX_DOMAIN_LENGTH} karakter olabilir")
        if len(note) > MAX_NOTE_LENGTH:
            raise _too_long(f"“{term}”: not en fazla {MAX_NOTE_LENGTH} karakter olabilir")
        if (key := fold(term)) in seen:
            raise VocabularyRejected(
                "vocabulary_term_duplicate",
                f"“{term}” iki kez var (satır {seen[key]} ve {n})",
            )
        seen[key] = n
        out.append({"term": term, "equivalents": equivalents, "domain": domain, "note": note})
    return out


def check_stopwords(items: object) -> list[StopwordItem]:
    """Clean stopwords: one word each (they are dropped token by token), no repeats (the
    source's ``check_stopwords``); the first of the folded-equal words stays with its group.
    """

    rows = _items(items)
    _check_shape(rows, VocabularyList.STOPWORDS)
    out: list[StopwordItem] = []
    seen: set[str] = set()
    for rec in rows:
        word = _text(rec.get("word"))
        if not word:
            continue
        if len(word.split()) > 1:
            raise VocabularyRejected(
                "vocabulary_stopword_not_single_word",
                f"“{word}”: durak kelime tek kelime olmalı",
            )
        group = _text(rec.get("group"))
        if len(word) > MAX_STOPWORD_LENGTH:
            raise _too_long(
                f"“{word}”: durak kelime en fazla {MAX_STOPWORD_LENGTH} karakter olabilir"
            )
        if len(group) > MAX_GROUP_LENGTH:
            raise _too_long(f"“{word}”: grup adı en fazla {MAX_GROUP_LENGTH} karakter olabilir")
        if (key := fold(word)) in seen:
            continue
        seen.add(key)
        out.append({"word": word, "group": group})
    return out


def check_list(kind: VocabularyList, items: object) -> list[dict[str, Any]]:
    if kind is VocabularyList.TERMS:
        return check_terms(items)
    return [dict(item) for item in check_stopwords(items)]


def list_digest(items: Sequence[Mapping[str, Any]]) -> str:
    """SHA-256 of the ordered items' stable JSON (Requirement 1): the list's content identity."""

    blob = json.dumps(list(items), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
