"""Rule-based Turkish report texts: reason, caveat, usage, notes (HANDOVER §9.6).

The rule engine's answer (no model, or the model failed); the analyst writes its own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vsa.expansion.query_expander import ExpandedQuery
from vsa.features import contains_sequence
from vsa.models import FlagKind, Level, Note, ObjectMatch, Verdict
from vsa.scoring.aggregate import CUSTOMER_KEYS
from vsa.scoring.rules import CAVEAT_DERIVATION
from vsa.text.normalize import fold, tokenize

USAGE = {
    Level.HIGH: "Talebin doğrudan karşılığı; öncelikli kaynak olarak kullanılabilir.",
    Level.MEDIUM: (
        "Kısıtlar kabul edilebilirse kullanılabilir; eksik kavramlar için diğer "
        "önerilerle birlikte değerlendirin."
    ),
    Level.LOW: "Yalnızca yardımcı kaynak veya türetme için değerlendirin.",
}


@dataclass(frozen=True, slots=True)
class Clarification:
    when: tuple[tuple[str, ...], ...]
    unless: tuple[tuple[str, ...], ...]
    question: str


def compile_clarifications(
    raw: Sequence[dict[str, object]], stopwords: frozenset[str]
) -> list[Clarification]:
    def phrases(key: str, item: dict[str, object]) -> tuple[tuple[str, ...], ...]:
        values = item.get(key) or []
        assert isinstance(values, list)
        out = (tuple(tokenize(str(v), stopwords=stopwords, keep_compound=False)) for v in values)
        return tuple(p for p in out if p)

    return [
        Clarification(phrases("when", it), phrases("unless", it), str(it["question"]).strip())
        for it in raw
    ]


def clarification_notes(q: ExpandedQuery, rules: Sequence[Clarification]) -> list[Note]:
    toks = tuple(q.tokens)
    notes = []
    for r in rules:
        if any(contains_sequence(toks, p) for p in r.when) and not any(
            contains_sequence(toks, p) for p in r.unless
        ):
            notes.append(Note("Netleştirme", "Talep netleştirilmeli", r.question))
    return notes


def explain(m: ObjectMatch, q: ExpandedQuery) -> None:
    """Fill reason / caveat / usage of an ObjectMatch in place."""
    content_n = len(q.content_concepts)
    best = m.columns[0]
    reasons: list[str] = []
    if content_n and m.covered:
        reasons.append(
            f"Talepteki {len(m.covered)}/{content_n} kavramı birlikte karşılıyor "
            f"({', '.join(m.covered)})."
        )
    lead = best.signals[0] if best.signals else "arama skoru en yüksek alan"
    reasons.append(f"En güçlü eşleşme {best.col.column}: {lead}.")
    time_hit = next((h for h in m.columns if h.role == "zaman"), None)
    tc = q.time_concept
    if tc is not None and time_hit is not None and m.components.get("time", 0) >= 0.8:
        reasons.append(f"{time_hit.col.column} kolonu ile {tc.value} seri sunuyor.")
    if m.long_format_values:
        reasons.append(f"Ürün kırılımı {m.dimension_column} kolonu üzerinden (uzun format).")
    if m.components.get("granularity") == 1.0:
        reasons.append("Müşteri seviyesinde anahtar içeriyor.")
    m.reason = " ".join(reasons)

    caveats: list[str] = []
    if m.missing:
        caveats.append("Karşılanmayan kavram: " + ", ".join(m.missing) + ".")
    if m.long_format_values:
        caveats.append(
            f"Kırılım uzun formatta: {', '.join(m.long_format_values)} değerleri "
            f"{m.dimension_column} kolonunda satır olarak beklenir; değerlerin varlığı "
            "ve adlandırması doğrulanmalı. Geniş format gerekiyorsa pivot uygulanmalı."
        )
    if tc is not None:
        t = m.components.get("time", 0.0)
        if t == 0:
            caveats.append(f"Talep edilen {tc.value} zaman boyutu için kolon yok.")
        elif t < 0.8 and time_hit is not None:
            caveats.append(
                f"Zaman kolonu ({time_hit.col.column}) düzenli {tc.value} seri olmayabilir."
            )
    if m.components.get("granularity") == 0.5:
        caveats.append("Müşteri seviyesi anahtar yok; işlem veya hesap seviyesinde olabilir.")
    # Same caveat on several columns -> one line listing them. "Needs derivation"
    # matters only for the leading column; on side columns it is noise.
    by_text: dict[str, list[str]] = {}
    for h in m.columns:
        for c in h.caveats:
            if c == CAVEAT_DERIVATION and h is not best:
                continue
            by_text.setdefault(c, []).append(h.col.column)
    for text, cols in by_text.items():
        caveats.append(f"{', '.join(cols)}: {text}" + ("" if text.endswith(".") else "."))
    m.caveat = "\n".join(caveats) if caveats else "-"
    m.usage = USAGE[m.level]


def join_suggestions(
    objects: Sequence[ObjectMatch],
    q: ExpandedQuery,
    keys_by_object: Mapping[str, Sequence[str]],
) -> list[Note]:
    """Two objects that together cover every concept and share a key (§8.3, early form)."""
    content = [c.label for c in q.content_concepts]
    if not content or not objects or not objects[0].missing:
        return []
    notes: list[Note] = []
    for i, a in enumerate(objects[:5]):
        for b in objects[i + 1 : 5]:
            if set(a.covered) | set(b.covered) < set(content):
                continue
            b_keys = set(keys_by_object.get(b.object_key, ()))
            keys = [k for k in keys_by_object.get(a.object_key, ()) if k in b_keys]
            if not any(fold(k) in CUSTOMER_KEYS for k in keys):
                continue
            notes.append(
                Note(
                    "Kapsam",
                    "Tablo birleştirme önerisi",
                    f"{a.object_name} + {b.object_name} birlikte tüm kavramları karşılıyor; "
                    f"{' + '.join(keys)} üzerinden birleştirilebilir. "
                    "Ortak anahtarın aynı anlamı taşıdığı doğrulanmalıdır.",
                )
            )
            return notes
    return notes


def quality_notes(objects: Sequence[ObjectMatch]) -> list[Note]:
    notes: list[Note] = []
    for m in objects:
        for h in m.columns:
            for f in h.col.flags:
                if f.kind is FlagKind.CORRECTED:
                    notes.append(Note("Veri kalitesi", f"{m.object_name}.{h.col.column}", f.text))
    return notes


def summary_sentence(verdict: Verdict, objects: Sequence[ObjectMatch]) -> str:
    if verdict is Verdict.NOT_FOUND or not objects:
        return (
            "BULUNAMADI — Sözlükte bu talebin doğrudan karşılığı bulunamadı. "
            "Talebi farklı ifadelerle yeniden deneyin veya veri ekibine iletin."
        )
    top = objects[0]
    if verdict is Verdict.FOUND:
        return (
            f"VAR — Talep en iyi {top.object_name} tablosuyla karşılanıyor "
            f"(güven %{round(top.score * 100)})."
        )
    gap = f" Eksik: {', '.join(top.missing)}." if top.missing else ""
    return (
        f"KISMEN VAR — En yakın karşılık {top.object_name} "
        f"(güven %{round(top.score * 100)}); kısıtlar için Notlar sekmesine bakın.{gap}"
    )


def key_columns(names: Sequence[str]) -> list[str]:
    """Columns that can serve as join keys: customer keys and the time column."""
    folded = {fold(n): n for n in names}
    keys = [folded[k] for k in sorted(CUSTOMER_KEYS) if k in folded]
    for t in ("period", "datadate"):
        if t in folded:
            keys.append(folded[t])
            break
    return keys
