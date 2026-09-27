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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from vsa.llm.analyst_prompts import (
    ANALYST_SCHEMA,
    CHUNK_SCHEMA,
    SHORTLIST_SCHEMA,
    analyst_system,
    analyst_user,
    chunk_system,
    chunk_user,
    reconcile_system,
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
    lines: dict[str, str] = field(default_factory=dict)  # object key -> its catalog line
    groups: dict[str, str] = field(default_factory=dict)  # object key -> dataset group


def _group(columns: Sequence[DictColumn]) -> str:
    groups = Counter(c.dataset_group for c in columns if c.dataset_group)
    return groups.most_common(1)[0][0] if groups else "-"


def build_catalog(objects: Mapping[str, Sequence[DictColumn]]) -> Catalog:
    lines: dict[str, str] = {}
    groups: dict[str, str] = {}
    ids: dict[str, str] = {}
    for i, key in enumerate(sorted(objects), 1):
        cols = objects[key]
        tid = f"T{i}"
        ids[tid] = key
        groups[key] = _group(cols)
        names = ", ".join(c.column for c in cols)
        lines[key] = f"{tid} | {key} | {groups[key]} | {len(cols)} kolon | {names}"
    return Catalog("\n".join(lines.values()), ids, {k: t for t, k in ids.items()}, lines, groups)


def chunk_catalog(catalog: Catalog, n: int) -> list[str]:
    """The catalog cut into ``n`` parts of similar size. Tables of one dataset group stay
    together (card tables with card tables), so each part can still compare relatives; a
    group larger than a part is split. Empty parts are dropped."""
    n = max(1, n)
    by_group: dict[str, list[str]] = defaultdict(list)
    for key in catalog.lines:
        by_group[catalog.groups[key]].append(key)
    size = {g: sum(len(catalog.lines[k]) for k in keys) for g, keys in by_group.items()}
    target = sum(size.values()) / n
    bins: list[list[str]] = [[] for _ in range(n)]
    load = [0] * n
    for group in sorted(by_group, key=lambda g: -size[g]):
        pieces = [by_group[group]]
        if size[group] > target * 1.2:  # too big for one part: spread it
            keys = by_group[group]
            parts = min(n, int(size[group] // target) + 1)
            pieces = [keys[i::parts] for i in range(parts)]
        for piece in pieces:
            i = load.index(min(load))
            bins[i] += piece
            load[i] += sum(len(catalog.lines[k]) for k in piece)
    order = {k: i for i, k in enumerate(catalog.lines)}
    ordered = [sorted(b, key=order.__getitem__) for b in bins if b]
    return ["\n".join(catalog.lines[k] for k in keys) for keys in ordered]


# --------------------------------------------------------------------------- step 1


@dataclass(slots=True)
class Shortlist:
    interpretation: str
    candidates: list[str]  # object keys, best first
    reasons: dict[str, str]
    confusables: list[str]
    search_terms: list[str]
    unknown_ids: int = 0
    # Information families of the request and their search terms: the pipeline runs a
    # table-level search per family, so a table the model overlooked in the catalog is
    # still read when its columns carry the family (e.g. PD / rating for "risk skoru").
    families: list[tuple[str, list[str]]] = field(default_factory=list)


def _picks(
    items: object, ids: Mapping[str, str], cap: int
) -> tuple[list[str], dict[str, str], int]:
    """Object keys the model picked (in order, at most ``cap``), their reasons, and how
    many ids were not among ``ids``."""
    out: list[str] = []
    why: dict[str, str] = {}
    unknown = 0
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        key = resolve_id(item.get("id"), ids)
        if key is None:
            unknown += 1
            log.warning("Analist listede olmayan id döndürdü: %s", item.get("id"))
            continue
        if key not in out and len(out) < cap:
            out.append(key)
            why[key] = str(item.get("why", "")).strip()
    return out, why, unknown


def _terms(value: object, cap: int) -> list[str]:
    return [str(t).strip() for t in (value if isinstance(value, list) else []) if str(t).strip()][
        :cap
    ]


def parse_shortlist(
    reply: Mapping[str, object],
    candidate_ids: Mapping[str, str],
    confusable_ids: Mapping[str, str],
    limit: int,
) -> Shortlist:
    cands, reasons, unknown = _picks(reply.get("candidates"), candidate_ids, limit)
    conf, _, unknown_conf = _picks(reply.get("confusables"), confusable_ids, limit)
    families: list[tuple[str, list[str]]] = []
    raw_families = reply.get("families")
    for fam in raw_families if isinstance(raw_families, list) else []:
        if isinstance(fam, dict) and (words := _terms(fam.get("terms"), 8)):
            families.append((str(fam.get("name", "")).strip() or "-", words))
    return Shortlist(
        interpretation=str(reply.get("interpretation", "")).strip(),
        candidates=cands,
        reasons=reasons,
        confusables=[k for k in conf if k not in cands],
        search_terms=_terms(reply.get("search_terms"), 12),
        unknown_ids=unknown + unknown_conf,
        families=families[:6],
    )


def shortlist(
    query: str, catalog: Catalog, hints: str, client: LLMClient, limit: int
) -> Shortlist | None:
    """Step 1 in one call: the whole catalog."""
    reply = client.chat_json(
        shortlist_system(catalog.text, limit),
        shortlist_user(query, hints),
        SHORTLIST_SCHEMA,
        max_tokens=2500,
    )
    return None if reply is None else parse_shortlist(reply, catalog.ids, catalog.ids, limit)


@dataclass(slots=True)
class ChunkRead:
    """Step 1a: what the parallel readers of the catalog parts proposed."""

    candidates: list[str]  # object keys, part by part
    reasons: dict[str, str]
    search_terms: list[str]
    parts: int
    failed: int
    unknown_ids: int = 0


def read_chunks(
    query: str, chunks: Sequence[str], client: LLMClient, per_chunk: int, ids: Mapping[str, str]
) -> ChunkRead | None:
    """Step 1a: every part of the catalog read at the same time, for recall. None only when
    every part failed; a failed part is counted and the others carry on."""

    def one(chunk: str) -> dict[str, object] | None:
        return client.chat_json(
            chunk_system(chunk, per_chunk), chunk_user(query), CHUNK_SCHEMA, max_tokens=1500
        )

    with ThreadPoolExecutor(max_workers=max(1, len(chunks))) as pool:
        replies = list(pool.map(one, chunks))
    if all(r is None for r in replies):
        return None
    read = ChunkRead([], {}, [], parts=len(chunks), failed=sum(r is None for r in replies))
    for reply in replies:
        if reply is None:
            continue
        keys, why, unknown = _picks(reply.get("candidates"), ids, per_chunk)
        read.unknown_ids += unknown
        for key in keys:
            if key not in read.reasons:
                read.candidates.append(key)
                read.reasons[key] = why[key]
        read.search_terms += [t for t in _terms(reply.get("search_terms"), 8)
                              if t not in read.search_terms]  # fmt: skip
    return read


def reconcile(
    query: str,
    pool: str,
    client: LLMClient,
    limit: int,
    pool_ids: Mapping[str, str],
    catalog_ids: Mapping[str, str],
) -> Shortlist | None:
    """Step 1b: the pooled candidates compared side by side; the final candidates, the
    reading of the request, its information families and look-alike tables."""
    reply = client.chat_json(
        reconcile_system(pool, limit), shortlist_user(query, "-"), SHORTLIST_SCHEMA,
        max_tokens=2500,
    )  # fmt: skip
    return None if reply is None else parse_shortlist(reply, pool_ids, catalog_ids, limit)


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
    evidence: str = "",
) -> str:
    """Every column with its description; for very wide tables only the relevant ones
    get a description and the rest are listed by name. ``evidence`` is a line under the
    heading (which request concepts the table carries, why it was added)."""
    head = f"### {tid} · {key} · Veri seti: {_group(columns)} · {len(columns)} kolon"
    if evidence:
        head += "\n" + evidence
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
# Sentence ends — but not the abbreviations "ör." and "vb.".
_SENTENCE = re.compile(r"(?<!\bör\.)(?<!\bvb\.)(?<=[.!?])\s+")
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
    derivation: str = ""  # batch: how to compute the field when no column holds it


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


def column_caveats(column: str, texts: Iterable[str]) -> list[str]:
    """Sentences of the model's warnings that name ``column`` — shown on the column and
    checked by the golden set's caveat traps."""
    pattern = re.compile(rf"\b{re.escape(column)}\b")
    out: list[str] = []
    for text in texts:
        for sentence in _SENTENCE.split(text):
            if pattern.search(sentence) and sentence not in out:
                out.append(sentence.strip())
    return out


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


class Cleaner:
    """Checks what the model wrote against the dictionary and counts what it drops:
    unknown ids and columns, and sentences naming a table or column that does not exist.
    Catalog ids left in the text ("T177 tablosu") are written as table names."""

    def __init__(
        self,
        checker: MentionChecker,
        ids: Mapping[str, str],
        columns_of: Mapping[str, Sequence[DictColumn]],
        catalog_ids: Mapping[str, str] | None = None,
    ) -> None:
        self.checker = checker
        self.ids = ids  # ids the model may choose from (the candidates)
        self.columns_of = columns_of
        self.names = catalog_ids or ids
        self.dropped = 0

    def _table_name(self, m: re.Match[str]) -> str:
        key = self.names.get(m.group(0))
        return key.rsplit(".", 1)[-1] if key else m.group(0)

    def text(self, value: object) -> str:
        raw = _CATALOG_ID.sub(self._table_name, str(value or "").strip())
        raw = _ECHO.sub(r"\1", raw)  # "T12 (vX)" became "vX (vX)"
        cleaned, n = self.checker.clean(raw)
        self.dropped += n
        return cleaned

    def bullets(self, value: object) -> list[str]:
        return [t for v in (value if isinstance(value, list) else []) if (t := self.text(v))]

    def notes(self, value: object) -> list[Note]:
        out: list[Note] = []
        for n in value if isinstance(value, list) else []:
            if not isinstance(n, dict):
                continue
            body = self.text(n.get("text"))
            title = self.text(n.get("title"))
            if body:
                out.append(Note(str(n.get("scope", "")).strip() or "Not", title or "-", body))
        return out

    def key(self, raw: object) -> str | None:
        key = resolve_id(raw, self.ids)
        if key is None:
            self.dropped += 1
            log.warning("Analist aday olmayan id önerdi: %s", raw)
        return key

    def columns(self, key: str, names: object) -> list[DictColumn]:
        table = {c.column: c for c in self.columns_of[key]}
        cols: list[DictColumn] = []
        for name in names if isinstance(names, list) else []:
            col = _resolve_column(str(name), table)
            if col is None:
                self.dropped += 1
                log.warning("Doğrulama: sözlükte olmayan alan düşürüldü: %s.%s", key, name)
            elif col not in cols:
                cols.append(col)
        return cols

    def recommendation(
        self, item: Mapping[str, object], min_confidence: float
    ) -> Recommendation | None:
        key = self.key(item.get("id"))
        if key is None:
            return None
        conf = _confidence(item.get("confidence"))
        if conf < min_confidence:
            return None
        cols = self.columns(key, item.get("columns"))
        if not cols:
            self.dropped += 1
            return None
        return Recommendation(
            object_key=key,
            columns=cols,
            covers=self.text(item.get("covers")),
            reason=self.text(item.get("reason")),
            caveat=without_typo_remarks(self.text(item.get("caveat"))) or "-",
            usage=self.text(item.get("usage")),
            confidence=conf,
            derivation=self.text(item.get("derivation")),
        )


_TYPO = ("yazim hata", "yazim yanlis", "typo")


def _is_typo_remark(text: str) -> bool:
    """A remark about misspelt column names (Dept/Debt): true but it changes no answer;
    models add them to warnings despite the prompt, so they are dropped here."""
    folded = fold(text)
    return any(t in folded for t in _TYPO)


def without_typo_remarks(text: str) -> str:
    return " ".join(s for s in _SENTENCE.split(text) if not _is_typo_remark(s)).strip()


def _confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _verdict_summary(said_raw: object, summary: str, found: bool) -> tuple[Verdict, str]:
    said = VERDICTS.get(str(said_raw or "").strip(), Verdict.PARTIAL)
    verdict = said
    if not found:
        verdict = Verdict.NOT_FOUND
        if said is not Verdict.NOT_FOUND:  # every suggestion fell to validation/threshold
            summary = "Talebi karşılayan, sözlükte doğrulanmış bir tablo bulunamadı."
    elif said is Verdict.NOT_FOUND:
        verdict = Verdict.PARTIAL
    return verdict, with_verdict(verdict, summary)


def with_verdict(verdict: Verdict, summary: str) -> str:
    """The summary starting with the verdict that stands, whatever the model wrote."""
    body = _VERDICT_PREFIX.sub("", summary).strip()
    return f"{verdict.value}. {body}".strip()


def build_answer(
    reply: Mapping[str, object],
    ids: Mapping[str, str],
    columns_of: Mapping[str, Sequence[DictColumn]],
    checker: MentionChecker,
    top_n: int,
    min_confidence: float,
    catalog_ids: Mapping[str, str] | None = None,
) -> AnalystAnswer:
    """The model's report with everything checked against the dictionary."""
    clean = Cleaner(checker, ids, columns_of, catalog_ids)
    recs: list[Recommendation] = []
    raw_recs = reply.get("recommendations")
    for item in raw_recs if isinstance(raw_recs, list) else []:
        if not isinstance(item, dict):
            continue
        rec = clean.recommendation(item, min_confidence)
        if rec is not None and all(r.object_key != rec.object_key for r in recs):
            recs.append(rec)
    recs.sort(key=lambda r: -r.confidence)
    recs = recs[:top_n]
    verdict, summary = _verdict_summary(
        reply.get("verdict"), clean.text(reply.get("summary")), bool(recs)
    )
    return AnalystAnswer(
        verdict=verdict,
        summary=summary,
        recommendations=recs,
        design=clean.bullets(reply.get("design")),
        attention=[a for a in clean.bullets(reply.get("attention")) if not _is_typo_remark(a)],
        notes=clean.notes(reply.get("notes")),
        dropped=clean.dropped,
    )


# --------------------------------------------------------------------------- batch

BATCH_STATUSES = ("Hazır", "Kısmen hazır", "Türetilmeli", "Bulunamadı")


@dataclass(slots=True)
class FieldAnswer:
    status: str  # one of BATCH_STATUSES
    candidates: list[Recommendation]


@dataclass(slots=True)
class BatchAnswer:
    summary: str
    said: str  # the model's verdict word; the final verdict follows the field statuses
    core: str | None
    fields: dict[int, FieldAnswer]
    design: list[str]
    attention: list[str]
    notes: list[Note]
    dropped: int = 0


def build_batch_answer(
    reply: Mapping[str, object],
    ids: Mapping[str, str],
    columns_of: Mapping[str, Sequence[DictColumn]],
    checker: MentionChecker,
    indexes: Iterable[int],
    min_confidence: float,
    catalog_ids: Mapping[str, str] | None = None,
    per_field: int = 3,
) -> BatchAnswer:
    """One chunk of a target-table analysis, checked against the dictionary. Fields the
    model skipped or answered with nothing valid are "Bulunamadı" (ADR-006)."""
    clean = Cleaner(checker, ids, columns_of, catalog_ids)
    wanted = set(indexes)
    fields: dict[int, FieldAnswer] = {}
    raw_fields = reply.get("fields")
    for item in raw_fields if isinstance(raw_fields, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index", -1))
        except (TypeError, ValueError):
            continue
        if index not in wanted or index in fields:
            continue
        cands: list[Recommendation] = []
        raw_cands = item.get("candidates")
        for c in raw_cands if isinstance(raw_cands, list) else []:
            if not isinstance(c, dict):
                continue
            rec = clean.recommendation(c, min_confidence)
            if rec is not None and all(r.object_key != rec.object_key for r in cands):
                cands.append(rec)
        cands.sort(key=lambda r: -r.confidence)
        status = str(item.get("status", "")).strip()
        if status not in BATCH_STATUSES:
            status = "Kısmen hazır"
        if not cands:
            status = "Bulunamadı"
        elif status == "Bulunamadı":
            status = "Kısmen hazır"
        fields[index] = FieldAnswer(status, cands[:per_field])
    for index in wanted - fields.keys():
        log.warning("Analist %d numaralı alanı cevaplamadı", index)
        fields[index] = FieldAnswer("Bulunamadı", [])
    core = resolve_id(reply.get("core"), ids)
    return BatchAnswer(
        summary=clean.text(reply.get("summary")),
        said=str(reply.get("verdict", "")).strip(),
        core=core,
        fields=fields,
        design=clean.bullets(reply.get("design")),
        attention=[a for a in clean.bullets(reply.get("attention")) if not _is_typo_remark(a)],
        notes=clean.notes(reply.get("notes")),
        dropped=clean.dropped,
    )
