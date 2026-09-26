"""Analyst flow (ADR-029): the LLM reads the warehouse the way an analyst does.

Search on columns finds tables that *mention* a concept; a person asking for "the
customer's credit card information" wants the tables that are *about* credit cards.
Rules cannot tell those apart reliably, a strong model reading the catalog can. So:

1. ``shortlist``: the model sees every table (name, group, column names) and picks
   candidate tables, look-alike tables and search terms for look-alike columns.
2. ``analyse``: the model reads every column description of the candidates plus the
   look-alike columns of the whole dictionary, and writes the report.
3. ``build_answer``: nothing the model wrote reaches the user unverified (ADR-002).
   Recommendations are candidate ids; columns must exist in their table; any sentence
   naming a table or column the dictionary does not have is removed and counted.

The rule pipeline stays: its ranking is shown to the model as hints, and it answers
alone when the model is off or fails (ADR-008). No file I/O here.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from vsa.llm.analyst_prompts import (
    ANALYST_SCHEMA,
    SHORTLIST_SCHEMA,
    analyst_system,
    analyst_user,
    shortlist_system,
    shortlist_user,
)
from vsa.llm.client import LLMClient
from vsa.models import DictColumn, FlagKind, Note, Verdict
from vsa.text.normalize import fold

log = logging.getLogger(__name__)

FLAG_TAG = {
    FlagKind.MODEL_ESTIMATED: "MODEL TAHMİNİ — DOĞRULANMALI",
    FlagKind.CORRECTED: "ORİJİNAL AÇIKLAMA HATALIYDI — DÜZELTİLDİ",
    FlagKind.NEEDS_VERIFICATION: "DOĞRULANMALI",
    FlagKind.NAMING_MISMATCH: "İSİM/İÇERİK UYUMSUZLUĞU",
}
# Columns every recommendation should be able to carry: record keys and time axes.
STRUCTURAL = frozenset(
    {
        "customerpartyid", "customerid", "accountnumber", "accountsuffix", "cardrefnumber",
        "maincustomerid", "maincustomerpartyid", "contractid", "datadate", "period",
        "trandate", "trndate", "transactiondate", "reportdate",
    }
)  # fmt: skip
SPREAD_MIN_TABLES = 4  # "Yaygınlık": the same column name in this many tables
CONFUSABLE_COLUMNS_PER_TABLE = 10
VERDICTS = {v.value: v for v in Verdict}


# --------------------------------------------------------------------------- catalog


@dataclass(frozen=True, slots=True)
class Catalog:
    text: str  # one line per table; identical for every request (prefix caching)
    ids: dict[str, str]  # "T12" -> object key
    keys: dict[str, str]  # object key -> "T12"


def _group(columns: Sequence[DictColumn]) -> str:
    groups = Counter(c.dataset_group for c in columns if c.dataset_group)
    return groups.most_common(1)[0][0] if groups else "-"


def build_catalog(objects: Mapping[str, Sequence[DictColumn]]) -> Catalog:
    lines: list[str] = []
    ids: dict[str, str] = {}
    for i, key in enumerate(sorted(objects), 1):
        cols = objects[key]
        tid = f"T{i}"
        ids[tid] = key
        names = ", ".join(c.column for c in cols)
        lines.append(f"{tid} | {key} | {_group(cols)} | {len(cols)} kolon | {names}")
    return Catalog("\n".join(lines), ids, {k: t for t, k in ids.items()})


# --------------------------------------------------------------------------- step 1


@dataclass(slots=True)
class Shortlist:
    interpretation: str
    candidates: list[str]  # object keys, best first
    reasons: dict[str, str]
    confusables: list[str]
    search_terms: list[str]
    unknown_ids: int = 0


def shortlist(
    query: str, catalog: Catalog, hints: str, client: LLMClient, limit: int
) -> Shortlist | None:
    reply = client.chat_json(
        shortlist_system(catalog.text, limit),
        shortlist_user(query, hints),
        SHORTLIST_SCHEMA,
        max_tokens=2500,
    )
    if reply is None:
        return None
    unknown = 0

    def keys(items: object, cap: int) -> tuple[list[str], dict[str, str]]:
        nonlocal unknown
        out: list[str] = []
        why: dict[str, str] = {}
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            key = resolve_id(item.get("id"), catalog.ids)
            if key is None:
                unknown += 1
                log.warning("Analist katalogda olmayan id döndürdü: %s", item.get("id"))
                continue
            if key not in out and len(out) < cap:
                out.append(key)
                why[key] = str(item.get("why", "")).strip()
        return out, why

    cands, reasons = keys(reply.get("candidates"), limit)
    conf, _ = keys(reply.get("confusables"), limit)
    terms = [str(t).strip() for t in reply.get("search_terms") or [] if str(t).strip()]
    return Shortlist(
        interpretation=str(reply.get("interpretation", "")).strip(),
        candidates=cands,
        reasons=reasons,
        confusables=[k for k in conf if k not in cands],
        search_terms=terms[:12],
        unknown_ids=unknown,
    )


# --------------------------------------------------------------------------- material


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def column_line(col: DictColumn, desc_chars: int) -> str:
    tags = [FLAG_TAG[f.kind] for f in col.flags if f.kind in FLAG_TAG]
    tag = f" [{'; '.join(tags)}]" if tags else ""
    kvkk = " [KVKK]" if col.has_pii else ""
    return f"- {col.column}{tag}{kvkk}: {_clip(col.description, desc_chars) or '(açıklama yok)'}"


def term_matcher(terms: Iterable[str]) -> Callable[[DictColumn], int]:
    """How many of the search terms a column mentions (name or description)."""
    folded = [fold(t) for t in terms if len(t.strip()) >= 3]

    def count(col: DictColumn) -> int:
        text = f"{fold(col.column)} {fold(col.description)}"
        return sum(1 for t in folded if t in text)

    return count


def table_material(
    key: str,
    tid: str,
    columns: Sequence[DictColumn],
    relevance: Mapping[int, float],
    desc_chars: int,
    full_limit: int,
) -> str:
    """Every column with its description; for very wide tables only the relevant ones
    get a description and the rest are listed by name."""
    head = f"### {tid} · {key} · Veri seti: {_group(columns)} · {len(columns)} kolon"
    if len(columns) <= full_limit:
        return "\n".join([head, *(column_line(c, desc_chars) for c in columns)])
    ranked = sorted(
        columns,
        key=lambda c: (-relevance.get(c.id, 0.0), -(fold(c.column) in STRUCTURAL), c.id),
    )
    shown = {c.id for c in ranked[:full_limit]}
    lines = [head, *(column_line(c, desc_chars) for c in columns if c.id in shown)]
    rest = [c.column for c in columns if c.id not in shown]
    lines.append(f"- Diğer {len(rest)} kolon (yalnız ad): {', '.join(rest)}")
    return "\n".join(lines)


def confusable_material(
    columns: Sequence[DictColumn],
    candidates: Iterable[str],
    confusable_tables: Sequence[str],
    relevance: Mapping[int, float],
    terms: Sequence[str],
    limit: int,
) -> str:
    """Look-alike columns outside the candidate tables: the model's evidence for the
    warnings ("Uyarı"), other candidates ("Top 5 dışı") and spread ("Yaygınlık")."""
    wanted = set(candidates)
    hits = term_matcher(terms)
    pool: list[tuple[float, DictColumn]] = []
    for c in columns:
        if c.object_key in wanted:
            continue
        s = relevance.get(c.id, 0.0) + hits(c)
        if s > 0:
            pool.append((s, c))
    pool.sort(key=lambda x: (-x[0], x[1].id))

    lines: list[str] = []
    per_table: dict[str, list[DictColumn]] = defaultdict(list)
    for key in confusable_tables:
        for _, c in pool:
            if c.object_key == key and len(per_table[key]) < CONFUSABLE_COLUMNS_PER_TABLE:
                per_table[key].append(c)
    if per_table:
        lines.append("Benzer görünen tablolar (1. adımda işaretlendi):")
        for key, cols in per_table.items():
            lines.append(f"* {key}")
            lines += [f"  {column_line(c, 240)}" for c in cols]
    seen = {c.id for cols in per_table.values() for c in cols}
    rest = [c for _, c in pool if c.id not in seen][:limit]
    if rest:
        lines.append("Benzer alanlar (tam adıyla):")
        lines += [f"- {c.object_key}.{column_line(c, 240)[2:]}" for c in rest]

    spread: dict[str, set[str]] = defaultdict(set)
    for _, c in pool:
        spread[c.column].add(c.object_name)
    common = sorted(
        ((n, t) for n, t in spread.items() if len(t) >= SPREAD_MIN_TABLES),
        key=lambda x: -len(x[1]),
    )[:8]
    if common:
        lines.append("Çok tabloda geçen alanlar:")
        lines += [f"- {n}: {len(t)} tablo ({', '.join(sorted(t)[:12])})" for n, t in common]
    return "\n".join(lines)


# --------------------------------------------------------------------------- validation


_FULL = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?\b")
_SHORT = re.compile(r"\b((?:v|rpt_)[A-Z]\w*)\.([A-Za-z_]\w*)\b")
_BARE = re.compile(r"\b((?:v|rpt_)[A-Z][A-Za-z0-9_]*)\b(?!\*)")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_CATALOG_ID = re.compile(r"\bT\d+\b")
_ECHO = re.compile(r"\b([\w.]+) \(\1\)")
_VERDICT_PREFIX = re.compile(r"^\s*(?:KISMEN VAR|VAR|BULUNAMADI|YOK)\b[\s.:—–-]*")


@dataclass(slots=True)
class MentionChecker:
    """Checks that every table / column named in free text exists (ADR-002)."""

    object_keys: frozenset[str]
    column_keys: frozenset[str]
    by_name: dict[str, set[str]] = field(default_factory=dict)  # object name -> keys
    columns_of: dict[str, set[str]] = field(default_factory=dict)  # object key -> columns

    @classmethod
    def build(cls, columns: Iterable[DictColumn]) -> MentionChecker:
        by_name: dict[str, set[str]] = defaultdict(set)
        cols: dict[str, set[str]] = defaultdict(set)
        col_keys: set[str] = set()
        for c in columns:
            by_name[c.object_name].add(c.object_key)
            cols[c.object_key].add(c.column)
            col_keys.add(c.key)
        return cls(frozenset(cols), frozenset(col_keys), dict(by_name), dict(cols))

    def unknown(self, text: str) -> list[str]:
        bad: list[str] = []
        rest = text
        for m in _FULL.finditer(text):
            name = m.group(0)
            if m.group(4) is None:
                # "Şema.Obje.Kolon" of a known object is fine too
                if name not in self.object_keys and not self._short_ok(m.group(2), m.group(3)):
                    bad.append(name)
            elif name not in self.column_keys:
                bad.append(name)
            rest = rest.replace(name, " ")
        for m in _SHORT.finditer(rest):
            if not self._short_ok(m.group(1), m.group(2)):
                bad.append(m.group(0))
            rest = rest.replace(m.group(0), " ")
        for m in _BARE.finditer(rest):
            if m.group(1) not in self.by_name:
                bad.append(m.group(1))
        return bad

    def _short_ok(self, obj: str, col: str) -> bool:
        keys = self.by_name.get(obj)
        if not keys:
            return False
        return any(col in self.columns_of[k] for k in keys)

    def clean(self, text: str) -> tuple[str, int]:
        """Text without the sentences that name something the dictionary lacks."""
        kept: list[str] = []
        dropped = 0
        for sentence in _SENTENCE.split(text.strip()):
            bad = self.unknown(sentence)
            if bad:
                dropped += 1
                log.warning("Doğrulama: sözlükte olmayan ad içeren cümle silindi: %s", bad)
            else:
                kept.append(sentence)
        return " ".join(kept).strip(), dropped


# --------------------------------------------------------------------------- step 2


@dataclass(slots=True)
class Recommendation:
    object_key: str
    columns: list[DictColumn]
    covers: str
    reason: str
    caveat: str
    usage: str
    confidence: float


@dataclass(slots=True)
class AnalystAnswer:
    verdict: Verdict
    summary: str
    recommendations: list[Recommendation]
    design: list[str]
    attention: list[str]
    notes: list[Note]
    dropped: int = 0  # unknown ids, columns and sentences removed by validation


def analyse(
    query: str,
    interpretation: str,
    material: str,
    confusables: str,
    client: LLMClient,
    top_n: int,
    max_tokens: int,
) -> dict[str, object] | None:
    return client.chat_json(
        analyst_system(top_n),
        analyst_user(query, interpretation, material, confusables),
        ANALYST_SCHEMA,
        max_tokens=max_tokens,
    )


def resolve_id(raw: object, ids: Mapping[str, str]) -> str | None:
    """Object key for what the model wrote as an id: the catalog id ("T12"), or — models
    sometimes write names instead — the full key or a table name that is unique among
    ``ids``. Anything outside ``ids`` is refused (ADR-002)."""
    text = str(raw or "").strip().strip("`'\"")
    if text in ids:
        return ids[text]
    keys = set(ids.values())
    if text in keys:
        return text
    named = [k for k in keys if fold(k.rsplit(".", 1)[-1]) == fold(text)]
    return named[0] if len(named) == 1 else None


def _resolve_column(name: str, columns: Mapping[str, DictColumn]) -> DictColumn | None:
    name = name.strip().strip("`'\"")
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    if name in columns:
        return columns[name]
    target = fold(name)
    return next((c for n, c in columns.items() if fold(n) == target), None)


def build_answer(
    reply: Mapping[str, object],
    ids: Mapping[str, str],
    columns_of: Mapping[str, Sequence[DictColumn]],
    checker: MentionChecker,
    top_n: int,
    min_confidence: float,
    catalog_ids: Mapping[str, str] | None = None,
) -> AnalystAnswer:
    """The model's report with everything checked against the dictionary. Catalog ids
    left in the text ("T177 tablosu") are written as table names."""
    dropped = 0
    names = catalog_ids or ids

    def table_name(m: re.Match[str]) -> str:
        key = names.get(m.group(0))
        return key.rsplit(".", 1)[-1] if key else m.group(0)

    def text(value: object) -> str:
        nonlocal dropped
        raw = _CATALOG_ID.sub(table_name, str(value or "").strip())
        raw = _ECHO.sub(r"\1", raw)  # "T12 (vX)" became "vX (vX)"
        cleaned, n = checker.clean(raw)
        dropped += n
        return cleaned

    recs: list[Recommendation] = []
    seen: set[str] = set()
    raw_recs = reply.get("recommendations")
    for item in raw_recs if isinstance(raw_recs, list) else []:
        if not isinstance(item, dict):
            continue
        key = resolve_id(item.get("id"), ids)
        if key is None or key in seen:
            dropped += key is None
            if key is None:
                log.warning("Analist aday olmayan id önerdi: %s", item.get("id"))
            continue
        try:
            conf = max(0.0, min(1.0, float(item.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        if conf < min_confidence:
            continue
        table = {c.column: c for c in columns_of[key]}
        cols: list[DictColumn] = []
        for name in item.get("columns") or []:
            col = _resolve_column(str(name), table)
            if col is None:
                dropped += 1
                log.warning("Doğrulama: sözlükte olmayan alan düşürüldü: %s.%s", key, name)
            elif col not in cols:
                cols.append(col)
        if not cols:
            dropped += 1
            continue
        seen.add(key)
        recs.append(
            Recommendation(
                object_key=key,
                columns=cols,
                covers=text(item.get("covers")),
                reason=text(item.get("reason")),
                caveat=text(item.get("caveat")) or "-",
                usage=text(item.get("usage")),
                confidence=conf,
            )
        )
    recs.sort(key=lambda r: -r.confidence)
    recs = recs[:top_n]

    def bullets(value: object) -> list[str]:
        return [t for v in (value if isinstance(value, list) else []) if (t := text(v))]

    notes: list[Note] = []
    raw_notes = reply.get("notes")
    for n in raw_notes if isinstance(raw_notes, list) else []:
        if not isinstance(n, dict):
            continue
        body = text(n.get("text"))
        title = text(n.get("title"))
        if body:
            notes.append(Note(str(n.get("scope", "")).strip() or "Not", title or "-", body))

    said = VERDICTS.get(str(reply.get("verdict", "")).strip(), Verdict.PARTIAL)
    summary = text(reply.get("summary"))
    verdict = said
    if not recs:
        verdict = Verdict.NOT_FOUND
        if said is not Verdict.NOT_FOUND:  # every suggestion fell to validation/threshold
            summary = "Talebi karşılayan, sözlükte doğrulanmış bir tablo bulunamadı."
    elif said is Verdict.NOT_FOUND:
        verdict = Verdict.PARTIAL
    body = _VERDICT_PREFIX.sub("", summary).strip()
    summary = f"{verdict.value}. {body}".strip()
    return AnalystAnswer(
        verdict=verdict,
        summary=summary,
        recommendations=recs,
        design=bullets(reply.get("design")),
        attention=bullets(reply.get("attention")),
        notes=notes,
        dropped=dropped,
    )
