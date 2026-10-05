"""Query processing: concepts + expansion (HANDOVER §7).

Two expansion sources in M1 (the LLM source arrives in M4):

(a) corporate term dictionary — bidirectional groups; a matched group adds its other
    members to the BM25 query at reduced weight;
(b) the dictionary's own synonym sections — inverted into phrase -> column ids; a
    phrase found in the query puts those columns straight into the candidate pool.

Per ADR-004 expansion only feeds the BM25 query; ``text`` keeps the user's original
wording.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from vsa.features import ColumnFeatures
from vsa.models import TermGroup
from vsa.text.normalize import fold, load_stopwords, tokenize, tokenize_pairs

# A single-word synonym shared by more columns than this is too generic to count
# as the "most reliable signal" (§7.2b); it still participates in BM25.
GENERIC_SYNONYM_DF = 40
MAX_PHRASE_LEN = 6
_WORD = re.compile(r"\w+")
_PARENS = re.compile(r"\(([^)]*)\)")
# Term-dictionary domains whose groups are measures, not content concepts.
MEASURE_DOMAINS = frozenset({"finansal"})
SCOPE_NOTE_PREFIX = "kapsam:"


class ConceptKind(StrEnum):
    TERM = "terim"
    TIME = "zaman"
    BREAKDOWN = "kırılım"
    MEASURE = "ölçü"



QUERY_ONLY_STOPWORDS = load_stopwords(["değil", "hariç", "dışında"])

@dataclass(frozen=True, slots=True)
class Concept:
    kind: ConceptKind
    label: str
    # A column satisfies the concept if ALL tokens of ANY alternative are present.
    alternatives: tuple[tuple[str, ...], ...] = ()
    value: str = ""  # TIME: "aylık"/"günlük"...; MEASURE: "oran"/"adet"/"tutar"
    # A requested breakdown value, e.g. "kredi kartı" in "kırılımlı (kredi kartı, …)".
    # Can be met by its own column (wide format) or a dimension column (long format).
    breakdown_value: bool = False
    # A term-dictionary note starting with "Kapsam:" — a known scope limit of the term
    # (e.g. virman covers in-bank transfers only). Reported as a caveat when matched.
    scope_note: str = ""

    @property
    def is_content(self) -> bool:
        """Content concepts count toward coverage; time/breakdown are scored apart."""
        return self.kind in (ConceptKind.TERM, ConceptKind.MEASURE)

    def display(self) -> str:
        kind = "kırılım değeri" if self.breakdown_value else self.kind.value
        return f"{kind}:{self.label}"


# (folded word prefix, canonical value). Prefix match on unstemmed folded tokens.
_TIME_WORDS: tuple[tuple[str, str], ...] = (
    ("aylik", "aylık"), ("monthly", "aylık"), ("ay sonu", "aylık"),
    ("gunluk", "günlük"), ("daily", "günlük"),
    ("haftalik", "haftalık"), ("weekly", "haftalık"),
    ("yillik", "yıllık"), ("yearly", "yıllık"), ("annual", "yıllık"),
    ("ceyrek", "çeyreklik"), ("quarter", "çeyreklik"),
    ("donemsel", "dönemsel"), ("periyodik", "dönemsel"),
)  # fmt: skip
_BREAKDOWN_WORDS = ("kirilim", "breakdown", "detay")
_MEASURE_WORDS: tuple[tuple[str, str], ...] = (
    ("oran", "oran"), ("yuzde", "oran"), ("rate", "oran"), ("ratio", "oran"),
    ("percent", "oran"),
    ("adet", "adet"), ("sayi", "adet"), ("count", "adet"),
    ("tutar", "tutar"), ("bakiye", "tutar"), ("amount", "tutar"), ("balance", "tutar"),
)  # fmt: skip
MEASURE_ALTERNATIVES: dict[str, tuple[tuple[str, ...], ...]] = {
    "oran": (("oran",), ("rate",), ("ratio",), ("yuzde",), ("percent",)),
    "adet": (("adet",), ("sayi",), ("count",), ("cnt",)),
    "tutar": (("tutar",), ("bakiy",), ("amount",), ("balanc",), ("toplam",)),
}


@dataclass(slots=True)
class ExpandedQuery:
    text: str
    tokens: list[str]  # stemmed content tokens of the original query, in order
    raw_words: frozenset[str]  # folded original words, for exact column-name match
    sparse_terms: dict[str, float]  # BM25 query: token -> weight
    concepts: list[Concept]
    term_groups: list[TermGroup]  # matched term-dictionary groups
    expansion_terms: list[str]  # display strings of added equivalents
    expansion_tokens: frozenset[str]  # tokens that came only from expansion
    synonym_hits: dict[int, list[str]] = field(default_factory=dict)  # col id -> phrases
    # Information weight per content concept (IDF over dictionary columns), set by the
    # engine. Rare concepts ("gayrimenkul") matter more than ubiquitous ones ("müşteri").
    concept_weights: dict[Concept, float] = field(default_factory=dict)
    unknown_concepts: list[Concept] = field(default_factory=list)  # appear nowhere

    def coverage(self, covered: Sequence[Concept]) -> float:
        """Information-weighted share of content concepts in ``covered`` (0–1)."""
        content = self.content_concepts
        if not content:
            return 0.0
        total = sum(self.concept_weights.get(c, 1.0) for c in content)
        got = sum(self.concept_weights.get(c, 1.0) for c in content if c in covered)
        return got / total if total else 0.0

    @property
    def content_concepts(self) -> list[Concept]:
        return [c for c in self.concepts if c.is_content]

    @property
    def time_concept(self) -> Concept | None:
        return next((c for c in self.concepts if c.kind is ConceptKind.TIME), None)

    @property
    def measure(self) -> str | None:
        c = next((c for c in self.concepts if c.kind is ConceptKind.MEASURE), None)
        return c.value if c else None

    @property
    def breakdown_values(self) -> list[Concept]:
        return [c for c in self.concepts if c.breakdown_value]

    @property
    def wants_breakdown(self) -> bool:
        return any(c.kind is ConceptKind.BREAKDOWN for c in self.concepts)


@dataclass(frozen=True, slots=True)
class _Phrase:
    tokens: tuple[str, ...]
    group: int
    member: str  # the term-dictionary string this phrase came from
    is_head: bool  # the group's own term (preferred on ties)


class QueryExpander:
    def __init__(
        self,
        term_groups: Sequence[TermGroup],
        features: Sequence[ColumnFeatures],
        stopwords: frozenset[str],
        expansion_weight: float = 0.6,
        enabled: bool = True,
        use_synonyms: bool = True,
    ) -> None:
        self.groups = list(term_groups)
        self.stopwords = stopwords
        self.weight = expansion_weight
        self.enabled = enabled
        self.use_synonyms = use_synonyms
        self._group_members: list[list[tuple[str, tuple[str, ...]]]] = []
        self._group_alts: list[tuple[tuple[str, ...], ...]] = []
        phrases: list[_Phrase] = []
        for gi, g in enumerate(self.groups):
            members = [(t, a) for t in g.all_terms if (a := self._phrase(t))]
            alts = tuple(dict.fromkeys(a for _, a in members))
            self._group_members.append(members)
            self._group_alts.append(alts)
            phrases.extend(_Phrase(a, gi, t, t == g.term) for t, a in members)
        # Longest first so "ihtiyaç kredisi" wins over "kredi"; on equal length a
        # group's own term wins over another group listing it as an equivalent.
        self._phrases = sorted(phrases, key=lambda p: (-len(p.tokens), not p.is_head))
        self._synonyms = build_synonym_index(features)

    @staticmethod
    def _phrase(text: str) -> tuple[str, ...]:
        # No stopword removal: "veri tarihi" must not shrink to "tarih" and then
        # fire on "doğum tarihi".
        return tuple(tokenize(text, keep_compound=False))

    def expand(self, text: str) -> ExpandedQuery:
        # "değil" stays in the stopword-free description tokens (it marks "X bazlı değil"
        # scope notes there) but is never a request concept: in "tüm limitler değil" it
        # would point the analyst at exactly the unwanted column.
        stop = self.stopwords | QUERY_ONLY_STOPWORDS
        pairs = tokenize_pairs(text, stopwords=stop, keep_compound=False)
        tokens = [t for t, _ in pairs]
        bm25_tokens = tokenize(text, stopwords=stop, keep_compound=True)
        raw_words = frozenset(fold(w).replace("_", "") for w in _WORD.findall(text))

        # Term dictionary off -> neither expansion nor multi-word term concepts.
        matches, consumed = self._match_terms(tokens) if self.enabled else ([], set())
        matched_groups = list(dict.fromkeys(gi for gi, _ in matches))
        concepts = self._concepts(pairs, matches, consumed)
        concepts = self._mark_breakdown_values(text, concepts)

        sparse: dict[str, float] = {t: 1.0 for t in bm25_tokens}
        expansion_terms: list[str] = []
        expansion_tokens: set[str] = set()
        if self.enabled:
            for gi in matched_groups:
                for member, alt in self._group_members[gi]:
                    new = [t for t in alt if t not in sparse]
                    if new:
                        expansion_terms.append(member)
                    for t in new:
                        sparse[t] = self.weight
                        expansion_tokens.add(t)

        hits = self._synonym_hits(tokens) if self.use_synonyms else {}
        return ExpandedQuery(
            text=text,
            tokens=tokens,
            raw_words=raw_words,
            sparse_terms=sparse,
            concepts=concepts,
            term_groups=[self.groups[i] for i in matched_groups],
            expansion_terms=list(dict.fromkeys(expansion_terms)),
            expansion_tokens=frozenset(expansion_tokens),
            synonym_hits=hits,
        )

    # ------------------------------------------------------------------ internals

    def _match_terms(self, tokens: list[str]) -> tuple[list[tuple[int, str]], set[int]]:
        """Greedy longest-first matching of term-dictionary phrases on query tokens.
        Returns (group index, matched member) in query order, and consumed positions."""
        consumed: set[int] = set()
        spans: list[tuple[int, int, str]] = []
        for ph in self._phrases:
            n = len(ph.tokens)
            for i in range(len(tokens) - n + 1):
                span = range(i, i + n)
                if tuple(tokens[i : i + n]) == ph.tokens and not consumed.intersection(span):
                    consumed.update(span)
                    spans.append((i, ph.group, ph.member))
        matches: list[tuple[int, str]] = []
        for _, gi, member in sorted(spans):
            if all(gi != g for g, _ in matches):
                matches.append((gi, member))
        return matches, consumed

    def _concepts(
        self,
        pairs: list[tuple[str, str]],
        matches: list[tuple[int, str]],
        consumed: set[int],
    ) -> list[Concept]:
        concepts: list[Concept] = []
        surfaces = [fold(surface) for _, surface in pairs]
        folded_text = " ".join(surfaces)
        special: set[int] = set()  # positions used by time/breakdown/measure words

        for prefix, value in _TIME_WORDS:
            if prefix in folded_text:
                concepts.append(Concept(ConceptKind.TIME, value, value=value))
                break
        for i, word in enumerate(surfaces):
            if word.startswith(_BREAKDOWN_WORDS):
                special.add(i)
                if not any(c.kind is ConceptKind.BREAKDOWN for c in concepts):
                    concepts.append(Concept(ConceptKind.BREAKDOWN, "kırılım"))
            if any(word.startswith(prefix) for prefix, _ in _TIME_WORDS):
                special.add(i)

        for gi, member in matches:
            g = self.groups[gi]
            if fold(g.domain) in MEASURE_DOMAINS:
                continue  # "tutar", "adet"… are measures, handled below
            scope = g.note if fold(g.note).startswith(SCOPE_NOTE_PREFIX) else ""
            concepts.append(
                Concept(
                    ConceptKind.TERM, member, alternatives=self._group_alts[gi], scope_note=scope
                )
            )

        for i, word in enumerate(surfaces):
            for prefix, value in _MEASURE_WORDS:
                if word.startswith(prefix):
                    if not any(c.kind is ConceptKind.MEASURE for c in concepts):
                        concepts.append(
                            Concept(
                                ConceptKind.MEASURE,
                                value,
                                alternatives=MEASURE_ALTERNATIVES[value],
                                value=value,
                            )
                        )
                    special.add(i)
                    break

        seen: set[str] = set()
        for i, (tok, surface) in enumerate(pairs):
            if i in consumed or i in special or tok in seen or tok.isdigit():
                continue
            seen.add(tok)
            concepts.append(Concept(ConceptKind.TERM, surface, alternatives=((tok,),)))
        return concepts

    def _mark_breakdown_values(self, text: str, concepts: list[Concept]) -> list[Concept]:
        """In a breakdown request, terms listed in parentheses are breakdown values:
        "kırılımlı olarak (kredi kartı, gayrimenkul, ihtiyaç kredisi vb.)"."""
        if not any(c.kind is ConceptKind.BREAKDOWN for c in concepts):
            return concepts
        listed: set[str] = set()
        for group in _PARENS.findall(text):
            listed.update(tokenize(group, stopwords=self.stopwords, keep_compound=False))
        if not listed:
            return concepts
        out = []
        for c in concepts:
            own = tokenize(c.label, keep_compound=False)
            if c.kind is ConceptKind.TERM and own and set(own) <= listed:
                c = replace(c, breakdown_value=True)
            out.append(c)
        return out

    def _synonym_hits(self, tokens: list[str]) -> dict[int, list[str]]:
        hits: dict[int, list[str]] = defaultdict(list)
        for n in range(min(MAX_PHRASE_LEN, len(tokens)), 0, -1):
            for i in range(len(tokens) - n + 1):
                phrase = tuple(tokens[i : i + n])
                entry = self._synonyms.get(phrase)
                if not entry:
                    continue
                if n == 1 and len(entry) > GENERIC_SYNONYM_DF:
                    continue
                label = " ".join(phrase)
                for col_id in entry:
                    if label not in hits[col_id]:
                        hits[col_id].append(label)
        return dict(hits)


def build_synonym_index(features: Iterable[ColumnFeatures]) -> dict[tuple[str, ...], list[int]]:
    """Synonym phrase (token tuple) -> column ids that list it (§7.2b)."""
    index: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for f in features:
        for phrase in dict.fromkeys(f.synonyms):
            if len(phrase) <= MAX_PHRASE_LEN:
                index[phrase].append(f.col.id)
    return dict(index)
