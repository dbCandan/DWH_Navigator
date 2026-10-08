"""Turkish text normalization (HANDOVER §6).

This module is the ONLY place where case folding happens. No other module may call
``str.lower()`` / ``str.upper()`` / ``str.casefold()`` directly.

Pipeline used for both indexing and querying::

    raw text -> CamelCase split -> Turkish lowercase -> ASCII fold
             -> stopword removal (token level) -> light suffix stemming

Both sides are ASCII-folded, so a user typing "musteri" matches "müşteri".
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})

_ASCII_FOLD = str.maketrans(
    {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
        # Not Turkish, but appear in banking text and should not break tokens.
        "é": "e",
        "è": "e",
        "ä": "a",
    }
)

# Suffixes in ASCII-folded form, longest first (HANDOVER §6.4).
# HANDOVER §6.4 list plus possessive+case stacks ("verisine", "tablosundan").
_SUFFIXES: tuple[str, ...] = tuple(
    sorted(
        set(
            "lerinin larinin lerine larina lerini larini lerin larin leri lari ler lar "
            "nin nun in un den dan ten tan de da te ta si su i u e a "
            "sinden sindan sinde sinda sine sina sini sinin ine ina ini "
            "nden ndan nde nda yla yle "
            "dir dur tir tur".split()  # copula: "oranıdır" -> "oran"
        ),
        key=lambda x: (-len(x), x),
    )
)
MIN_STEM_LEN = 4
_MAX_STEM_PASSES = 3

# A "word" is a run of letters/digits; everything else separates words.
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
# An identifier may also contain underscores (KKB_DATE).
_IDENT_RE = re.compile(r"\w+", re.UNICODE)


def tr_lower(text: str) -> str:
    """Lowercase with Turkish rules: ``I -> ı`` and ``İ -> i``."""
    return text.translate(_TR_LOWER).lower()


def ascii_fold(text: str) -> str:
    """Fold Turkish characters to ASCII. Expects already-lowercased text."""
    return text.translate(_ASCII_FOLD)


def fold(text: str) -> str:
    """Turkish lowercase + ASCII fold. Canonical comparison form for any string."""
    return ascii_fold(tr_lower(text))


def split_camel(word: str) -> list[str]:
    """Split a CamelCase / snake_case identifier into its parts (original casing kept).

    ``CardLimitFullnessToday`` -> ``Card Limit Fullness Today``
    ``IFRSStage``              -> ``IFRS Stage`` (acronym run is kept together)
    ``TOTALOUTSTANDINGBALANCE``-> unchanged (all caps cannot be split)
    ``KKB_DATE``               -> ``KKB DATE``
    ``Avg30d``                 -> ``Avg 30 d``
    """
    parts: list[str] = []
    for chunk in _WORD_RE.findall(word):
        parts.extend(_split_chunk(chunk))
    return parts


def _split_chunk(chunk: str) -> list[str]:
    parts: list[str] = []
    start = 0
    n = len(chunk)
    for i in range(1, n):
        prev, cur = chunk[i - 1], chunk[i]
        nxt = chunk[i + 1] if i + 1 < n else ""
        boundary = (
            (prev.islower() and cur.isupper())
            or (prev.isdigit() != cur.isdigit())
            # End of an acronym run: "IFRSStage" -> split before "S" of "Stage".
            or (prev.isupper() and cur.isupper() and nxt.islower())
        )
        if boundary:
            parts.append(chunk[start:i])
            start = i
    parts.append(chunk[start:])
    return parts


def stem(token: str) -> str:
    """Light rule-based Turkish suffix stripping on an ASCII-folded token.

    Strips the longest matching suffix while the remaining root keeps at least
    ``MIN_STEM_LEN`` characters; repeats a few times so stacked suffixes
    ("transferlerinin" -> "transfer") reduce consistently. Digits are left alone.
    """
    if token.isdigit():
        return token
    for _ in range(_MAX_STEM_PASSES):
        for suffix in _SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= MIN_STEM_LEN:
                token = token[: -len(suffix)]
                break
        else:
            break
    return token


def load_stopwords(lines: Iterable[str]) -> frozenset[str]:
    """Build a stopword set from words (blanks skipped).

    Holds both the folded and the stemmed form, so inflected fillers such as
    "bilgilerini" are caught by the entry "bilgisi" (both stem to "bilgi").
    """
    words: set[str] = set()
    for line in lines:
        word = line.strip()
        if word:
            folded = fold(word)
            words.update((folded, stem(folded)))
    return frozenset(words)


def tokenize_pairs(
    text: str,
    *,
    stopwords: frozenset[str] = frozenset(),
    do_stem: bool = True,
    keep_compound: bool = True,
) -> list[tuple[str, str]]:
    """Like :func:`tokenize`, but each token comes with its surface form
    (Turkish-lowercased original word part) for human-readable labels."""
    pairs: list[tuple[str, str]] = []
    for word in _IDENT_RE.findall(text):
        parts = split_camel(word)
        for part in parts:
            tok = fold(part)
            if (len(tok) < 2 and not tok.isdigit()) or tok in stopwords:
                continue
            stemmed = stem(tok)
            if stemmed in stopwords:
                continue
            pairs.append((stemmed if do_stem else tok, tr_lower(part)))
        if keep_compound and len(parts) > 1:
            # Whole identifier, never stemmed: it must match the name exactly.
            pairs.append((fold(word.replace("_", "")), tr_lower(word)))
    return pairs


def tokenize(
    text: str,
    *,
    stopwords: frozenset[str] = frozenset(),
    do_stem: bool = True,
    keep_compound: bool = True,
) -> list[str]:
    """Turn free text or an identifier into normalized search tokens.

    Stopwords are removed per token, not per phrase: in "risk bilgisi" only
    "bilgisi" is dropped (HANDOVER §6.5).

    With ``keep_compound`` a CamelCase word also emits its whole folded form, so
    an exact identifier query (``CreditCardLimitRate``) still matches.
    """
    return [
        t
        for t, _ in tokenize_pairs(
            text, stopwords=stopwords, do_stem=do_stem, keep_compound=keep_compound
        )
    ]
