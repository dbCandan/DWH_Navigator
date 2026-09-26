"""Batch mode: a target-table request, field by field (HANDOVER §4.1, §9.4, M5).

pass 1  every field is searched on its own (TR title + EN title + description)
core    candidate objects are scored for the whole request:
            core_score = Σ field scores × time fit
        A monthly target table needs a monthly source, so the time grain is a
        multiplier, not a tie-breaker ("tek tablo kapsama").
pass 2  every field is re-scored with the core candidates forced into its
        candidate set; core tables get a context bonus, because a generic field
        ("Period", "CustomerId") only makes sense inside the table that serves the
        rest of the request. Structural fields (customer key, time) are taken from
        the core table when it has them (ADR-016).
status  Hazır / Kısmen hazır / Türetilmeli / Bulunamadı, with a derivation hint
        (COUNT(DISTINCT <entity column>), COUNT(*), SUM(…)) when no ready column exists
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from vsa.expansion.query_expander import Concept, ConceptKind, ExpandedQuery
from vsa.features import ColumnFeatures
from vsa.models import (
    BatchResult,
    ColumnHit,
    FieldCandidate,
    FieldResult,
    FieldStatus,
    Note,
    ObjectMatch,
    RequestField,
    TableCoverage,
    Verdict,
)
from vsa.pipeline import Engine
from vsa.scoring.aggregate import CUSTOMER_KEYS, ObjectColumns, time_component
from vsa.scoring.explain import clarification_notes, explain
from vsa.text.normalize import fold, split_camel, stem, tokenize, tokenize_pairs, tr_lower
from vsa.validate import validate

SERVE_MIN = 0.50  # an object "serves" a field when its field score reaches this
READY_MIN = 0.80
CORE_CANDIDATES = 8  # objects forced into every field's candidate set in pass 2
CORE_TABLES = 3  # of which the best ones get a context bonus
CORE_BONUS = 0.10
NEAR_CORE_BONUS = 0.05
WIDE_MIN_COLUMNS = 3  # lead + siblings sharing its measure and a name part
DOMAIN_BONUS = 0.10  # derivation source in the core table's dataset group
CORE_WIDE_MIN = 0.45  # core table's own score needed to answer from its column family
ASSESS_CANDIDATES = 8  # candidates whose measure fit is judged before the final cut
DIRECTION_BONUS = 0.05  # ± for Outgoing/Incoming tables vs "gönderilen"/"gelen" fields
MISFIT_PENALTY = 0.15  # same size as the column-level derivation penalty (§9.2)


def _stems(*words: str) -> frozenset[str]:
    return frozenset(stem(fold(w)) for w in words)


DISTINCT_WORDS = _stems("farklı", "distinct", "tekil", "unique")
COUNT_WORDS = _stems("sayı", "sayısı", "count", "adet", "adedi", "cnt")
TOTAL_WORDS = _stems("toplam", "toplamı", "total", "sum", "tutar", "amount")
COUNT_COLUMN = _stems("count", "cnt", "adet", "sayi", "numberof")
AMOUNT_COLUMN = _stems("amount", "amounttl", "tutar", "total", "sum", "balance")
DISTINCT_COLUMN = _stems("distinct", "unique", "farkli")
GENERIC_NAME_PARTS = COUNT_COLUMN | AMOUNT_COLUMN | _stems("tl", "id", "name", "l12m", "l6m")

# Entities a "farklı X sayısı" field counts, and the column-name parts that hold them.
ENTITIES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    # entity: (field words, column-name parts)
    "banka": (_stems("banka", "bank"), _stems("bank", "banka")),
    "kişi": (
        _stems("alıcı", "kişi", "person", "receiver", "gönderen", "sender"),
        _stems("identity", "receiver", "person", "kisi", "alici", "sender", "beneficiary"),
    ),
}

# The entity column must name or identify the entity …
ENTITY_VALUE_PARTS = _stems("name", "code", "kod", "id", "identity", "number", "no", "adi", "title")
# … and not be the number of something else that merely mentions it.
NOT_ENTITY_PARTS = _stems("card", "kart", "account", "hesap", "iban", "phone", "telefon")

PERIOD_FIELDS = frozenset({"period", "donem", "periyot", "ay", "yearmonth", "month"})
DAILY_FIELDS = frozenset({"date", "gun", "tarih", "day", "trandate", "datadate"})
KEY_FIELDS = frozenset(
    {*CUSTOMER_KEYS, "cif", "customerno", "musterino", "musterinumarasi", "musteri"}
)


@dataclass(slots=True)
class _FieldRun:
    field: RequestField
    query: str
    q: ExpandedQuery
    matches: dict[str, ObjectMatch]


@dataclass(frozen=True, slots=True)
class _Core:
    key: str
    score: float
    time_fit: float
    served: list[str]


# --------------------------------------------------------------------------- helpers


def field_query(f: RequestField) -> str:
    """TR title + humanized EN title (when it adds something) + description."""
    en = " ".join(split_camel(f.en)) if f.en else ""
    if en and fold(en.replace(" ", "")) == fold(f.tr.replace(" ", "")):
        en = ""
    return " ".join(p for p in (f.tr, en, f.description) if p)


def _names(f: RequestField) -> set[str]:
    return {fold(f.en).replace("_", ""), fold(f.tr).replace(" ", "")}


def time_grain(fields: Sequence[RequestField]) -> tuple[str, RequestField | None]:
    """The request's time grain from its time field: Period -> aylık, Date -> günlük."""
    for f in fields:
        if _names(f) & PERIOD_FIELDS:
            return "aylık", f
        if _names(f) & DAILY_FIELDS:
            return "günlük", f
    return "", None


def is_key_field(f: RequestField) -> bool:
    return bool(_names(f) & KEY_FIELDS)


def _field_tokens(f: RequestField) -> set[str]:
    return set(tokenize(f"{f.tr} {' '.join(split_camel(f.en))}", keep_compound=False))


def field_kind(f: RequestField) -> set[str]:
    toks = _field_tokens(f)
    kinds = set()
    if toks & DISTINCT_WORDS:
        kinds.add("distinct")
    if toks & COUNT_WORDS:
        kinds.add("count")
    if toks & TOTAL_WORDS:
        kinds.add("total")
    return kinds


def field_entity(f: RequestField) -> str | None:
    toks = _field_tokens(f)
    for entity, (words, _) in ENTITIES.items():
        if toks & words:
            return entity
    return None


OUT_WORDS = ("gonder", "giden", "outgoing", "sent", "sender")
IN_WORDS = ("gelen", "incoming", "alinan", "received")


def field_direction(f: RequestField) -> str:
    """Transfer direction a field asks for: "out", "in", or "" (none / both)."""
    words = fold(f"{f.tr} {f.description} {' '.join(split_camel(f.en))}").replace("/", " ").split()
    out = any(w.startswith(OUT_WORDS) for w in words)
    inc = any(w.startswith(IN_WORDS) for w in words)
    return "out" if out and not inc else "in" if inc and not out else ""


def direction_fit(direction: str, object_name: str) -> int:
    """+1 when the table's name carries the asked direction, -1 for the opposite one."""
    if not direction:
        return 0
    name = fold(object_name)
    has_out, has_in = "outgoing" in name, "incoming" in name
    if direction == "out":
        return 1 if has_out else -1 if has_in else 0
    return 1 if has_in else -1 if has_out else 0


def column_kind(f: ColumnFeatures) -> set[str]:
    kinds = set()
    if f.name_tokens & DISTINCT_COLUMN:
        kinds.add("distinct")
    if f.name_tokens & COUNT_COLUMN or f.name_folded.endswith(("count", "cnt")):
        kinds.add("count")
    if f.name_tokens & AMOUNT_COLUMN or f.name_folded.endswith(("amount", "amounttl")):
        kinds.add("total")
    return kinds


def entity_column(obj: ObjectColumns, entity: str) -> ColumnFeatures | None:
    """A non-aggregate column holding the entity (ReceiverBankName, ReceiverIdentityNumber).
    Card/account numbers that merely mention a bank ("BankCardNo") do not qualify."""
    parts = ENTITIES[entity][1]
    for f in obj.features:
        if (
            f.name_tokens & parts
            and f.name_tokens & ENTITY_VALUE_PARTS
            and not f.name_tokens & NOT_ENTITY_PARTS
            and not column_kind(f)
        ):
            return f
    return None


def wide_siblings(obj: ObjectColumns, lead: ColumnFeatures) -> list[str]:
    """Columns sharing the lead's measure and a specific name part (Ek A.3:
    FASTIncomingCount, KASIncomingCount, … — a breakdown encoded in names)."""
    kinds = column_kind(lead) & {"count", "total"}
    parts = lead.name_tokens - GENERIC_NAME_PARTS - {lead.name_folded}
    if not kinds or not parts:
        return []
    return [
        f.col.column
        for f in obj.features
        if f is not lead and column_kind(f) & kinds and (f.name_tokens - {f.name_folded}) & parts
    ]


# --------------------------------------------------------------------------- analyzer


class BatchAnalyzer:
    def __init__(self, engine: Engine, top_n: int = 3) -> None:
        self.engine = engine
        self.top_n = top_n

    def _run(self, f: RequestField, include: Sequence[str] = ()) -> _FieldRun:
        query = field_query(f)
        ranked, q = self.engine.rank_objects(query, include=include)
        ranked, _ = validate(ranked, self.engine.column_keys)
        return _FieldRun(f, query, q, {m.object_key: m for m in ranked})

    def _time_fit(self, key: str, grain: str) -> tuple[float, ColumnFeatures | None]:
        if not grain:
            return 1.0, None
        concept = Concept(ConceptKind.TIME, grain, value=grain)
        return time_component(self.engine.objects[key], concept)

    def _cores(self, runs: Sequence[_FieldRun], grain: str) -> list[_Core]:
        keys = {k for run in runs for k in run.matches}
        cores = []
        for key in keys:
            total = sum(run.matches[key].score for run in runs if key in run.matches)
            fit = self._time_fit(key, grain)[0]
            served = [
                run.field.label
                for run in runs
                if key in run.matches and run.matches[key].score >= SERVE_MIN
            ]
            cores.append(_Core(key, total * (0.5 + 0.5 * fit), fit, served))
        cores.sort(key=lambda c: (-c.score, c.key))
        return cores

    def analyze(self, fields: Sequence[RequestField], name: str = "Talep") -> BatchResult:
        started = time.perf_counter()
        grain, grain_field = time_grain(fields)

        first = [self._run(f) for f in fields]
        candidates = [c.key for c in self._cores(first, grain)[:CORE_CANDIDATES]]
        runs = [self._run(f, include=candidates) for f in fields]
        cores = self._cores(runs, grain)
        bonus = {
            c.key: (CORE_BONUS if i == 0 else NEAR_CORE_BONUS)
            for i, c in enumerate(cores[:CORE_TABLES])
        }
        core = cores[0] if cores else None

        results = [self._field_result(run, bonus, core, grain, grain_field) for run in runs]
        coverage = self._coverage(cores[:5], runs)
        notes = self._notes(runs, results, coverage, grain, grain_field)
        verdict, summary = self._summary(results, coverage)
        return BatchResult(
            name=name,
            verdict=verdict,
            summary=summary,
            fields=results,
            coverage=coverage,
            notes=notes,
            time_grain=grain,
            dictionary_source=Path(self.engine.dictionary.source_path).name,
            dictionary_version=self.engine.dictionary.version,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            method=[
                "Her alan TR başlık + EN başlık + açıklama ile ayrı ayrı arandı.",
                "Çekirdek tablo: alan skorlarının toplamı × talebin zaman düzeyine uyum "
                "(aylık talep için Period, günlük talep için işlem tarihi).",
                f"Çekirdek adaylar her alan için ayrıca skorlandı; bağlam bonusu "
                f"+{CORE_BONUS:.2f} (1. tablo) / +{NEAR_CORE_BONUS:.2f} (2.–3. tablo).",
                "Müşteri anahtarı ve zaman alanı, varsa çekirdek tablodan alınır.",
                "Durum: Hazır ≥ %80 ve türetme yok; Kısmen hazır: %50–79 veya kısıtlı; "
                "Türetilmeli: hazır alan yok, hesaplanabilir; Bulunamadı: eşik altı.",
                "LLM: kullanılmadı",
            ],
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )

    # ------------------------------------------------------------------ per field

    def _field_result(
        self,
        run: _FieldRun,
        bonus: dict[str, float],
        core: _Core | None,
        grain: str,
        grain_field: RequestField | None,
    ) -> FieldResult:
        s = self.engine.settings.scoring
        cands = [
            FieldCandidate(
                match=m,
                score=m.score + (bonus.get(k, 0.0) if m.score >= SERVE_MIN else 0.0),
                in_core=k in bonus,
            )
            for k, m in run.matches.items()
        ]
        cands.sort(key=lambda c: (-c.score, c.match.object_key))

        cands = self._merge(cands, self._distinct_candidates(run, core))
        # "Gönderilen / gelen": Outgoing vs Incoming tables.
        direction = field_direction(run.field)
        if direction:
            for c in cands:
                c.score += DIRECTION_BONUS * direction_fit(direction, c.match.object_name)
            cands.sort(key=lambda c: (-c.score, c.match.object_key))
        structural = self._structural(run, core, grain, grain_field)
        preferred = structural or self._core_wide(run, core)
        if preferred is not None:
            key = preferred.match.object_key
            cands = [preferred, *(c for c in cands if c.match.object_key != key)]

        # Judge the measure fit of the leading candidates before the final cut: a
        # distinct-count field cannot be answered by an amount column.
        head = cands[:ASSESS_CANDIDATES]
        for c in head:
            self._derivation(run.field, c)
            if not c.fits_measure:
                c.score -= MISFIT_PENALTY
        # A candidate that cannot deliver the requested measure ranks after every one
        # that can, whatever its text similarity.
        cands = sorted(head, key=lambda c: (not c.fits_measure, -c.score, c.match.object_key))
        if preferred is not None:
            cands = [preferred, *(c for c in cands if c is not preferred)]
        cands = [c for c in cands if c.score >= s.min_candidate_score][: self.top_n]
        for c in cands:
            c.score = max(0.0, min(1.0, c.score))
            explain(c.match, run.q)

        status = self._status(cands, s.min_answer_score, structural is not None)
        return FieldResult(run.field, status, cands if status is not FieldStatus.NOT_FOUND else [])

    @staticmethod
    def _merge(
        cands: list[FieldCandidate], extra: Sequence[FieldCandidate]
    ) -> list[FieldCandidate]:
        by_key = {c.match.object_key: c for c in cands}
        for e in extra:
            have = by_key.get(e.match.object_key)
            if have is None:
                by_key[e.match.object_key] = e
            elif not have.derivation:
                have.derivation = e.derivation
                have.match = e.match
        return sorted(by_key.values(), key=lambda c: (-c.score, c.match.object_key))

    def _groups(self, key: str) -> set[str]:
        return {g for f in self.engine.objects[key].features if (g := f.col.dataset_group)}

    def _distinct_candidates(self, run: _FieldRun, core: _Core | None) -> list[FieldCandidate]:
        """ "Farklı banka / alıcı sayısı": search the entity itself and offer
        COUNT(DISTINCT <entity column>) from tables that carry it (Ek A.3). Tables in
        the core table's data domain (dataset group) are always considered and get a
        domain bonus: the derivation must come from the same kind of data."""
        entity = field_entity(run.field)
        if "distinct" not in field_kind(run.field) or entity is None:
            return []
        domain = self._groups(core.key) if core else set()
        in_domain = {
            k
            for k, obj in self.engine.objects.items()
            if domain & self._groups(k) and entity_column(obj, entity) is not None
        }
        drop = DISTINCT_WORDS | COUNT_WORDS
        words = [t for t, _ in tokenize_pairs(run.query, keep_compound=False) if t not in drop]
        ranked, _ = self.engine.rank_objects(" ".join(words), include=sorted(in_domain))
        ranked, _ = validate(ranked, self.engine.column_keys)
        out = []
        for m in ranked:
            col = entity_column(self.engine.objects[m.object_key], entity)
            if col is None:
                continue
            bonus = DOMAIN_BONUS if m.object_key in in_domain else 0.0
            c = FieldCandidate(
                match=m,
                score=m.score + bonus,
                in_core=bool(bonus),
                derivation=f"COUNT(DISTINCT {col.col.column})",
            )
            self._promote(c, col)
            out.append(c)
        return out

    def _core_wide(self, run: _FieldRun, core: _Core | None) -> FieldCandidate | None:
        """A count/total field that the core table holds as a family of per-channel
        columns (FASTIncomingCount, KASOutgoingCount, …): answer from the core table,
        summing the family, so the target table stays buildable from one source."""
        wanted = field_kind(run.field) & {"count", "total"}
        if (
            core is None
            or core.key not in run.matches
            or not wanted
            or "distinct" in field_kind(run.field)
        ):
            return None
        m = run.matches[core.key]
        if m.score < CORE_WIDE_MIN:
            return None
        obj = self.engine.objects[core.key]
        feats = {f.col.id: f for f in obj.features}
        lead = feats[m.columns[0].col.id]
        if not column_kind(lead) & wanted:
            return None
        # The family must carry the field's specific terms: "kendi hesabına transfer
        # sayısı" is not answered by a family of all-transfer counts.
        specific = [c for c in run.q.content_concepts if len(c.alternatives) > 1]
        if any(c.label not in m.columns[0].concepts for c in specific):
            return None
        family = wide_siblings(obj, lead)
        if len(family) + 1 < WIDE_MIN_COLUMNS:
            return None
        return FieldCandidate(
            match=m, score=max(m.score, SERVE_MIN) + CORE_BONUS, in_core=True, wide_family=True
        )

    def _structural(
        self,
        run: _FieldRun,
        core: _Core | None,
        grain: str,
        grain_field: RequestField | None,
    ) -> FieldCandidate | None:
        """Customer key / time field answered by the core table's own column (ADR-016)."""
        if core is None or core.key not in run.matches:
            return None
        m = run.matches[core.key]
        obj = self.engine.objects[core.key]
        column: ColumnFeatures | None = None
        note = ""
        if run.field is grain_field:
            fit, column = self._time_fit(core.key, grain)
            if fit < 0.8 or column is None:
                return None
            note = (
                f"Talebin {grain} zaman alanı çekirdek tablonun {column.col.column} "
                "kolonuyla karşılanır."
            )
        elif is_key_field(run.field):
            wanted = _names(run.field)
            keys = [f for f in obj.features if f.name_folded in CUSTOMER_KEYS]
            keys.sort(
                key=lambda f: (f.name_folded not in wanted, f.name_folded != "customerpartyid")
            )
            column = keys[0] if keys else None
            if column is None:
                return None
            note = (
                f"Müşteri anahtarı çekirdek tablonun {column.col.column} kolonudur "
                "(müşteri no = hesap no, ADR-009)."
            )
        if column is None:
            return None
        hit = next((h for h in m.columns if h.col.id == column.col.id), None)
        hit = hit or ColumnHit(column.col, 0.0, m.score, role="yapısal")
        m.columns = [hit, *(h for h in m.columns if h is not hit)]
        return FieldCandidate(match=m, score=max(m.score, READY_MIN), in_core=True, notes=[note])

    def _derivation(self, f: RequestField, c: FieldCandidate) -> None:
        """Ready aggregate, derivation hint, or wide-format note (Ek A.3)."""
        wanted = field_kind(f)
        obj = self.engine.objects[c.match.object_key]
        feats = {x.col.id: x for x in obj.features}
        lead = feats[c.match.columns[0].col.id]
        have = column_kind(lead)
        entity = field_entity(f)

        if c.derivation:
            pass  # already set by the distinct-entity search
        elif "distinct" in wanted and entity:
            ready = "count" in have and lead.name_tokens & ENTITIES[entity][1]
            if not ready:
                target = entity_column(obj, entity)
                if target is not None:
                    c.derivation = f"COUNT(DISTINCT {target.col.column})"
                    self._promote(c, target)
                else:
                    c.fits_measure = False
            else:
                c.notes.append(
                    f"{lead.col.column} hazır bir {entity} sayısıdır; tekil (distinct) sayım "
                    "olduğu doğrulanmalı."
                )
        elif "count" in wanted and "total" not in wanted and "count" not in have:
            c.derivation = "COUNT(*)"
        elif "total" in wanted and "count" not in wanted and "total" not in have:
            amount = next((x for x in obj.features if "total" in column_kind(x)), None)
            if amount is not None:
                c.derivation = f"SUM({amount.col.column})"
                self._promote(c, amount)

        if not c.derivation:
            siblings = wide_siblings(obj, lead)
            if len(siblings) + 1 >= WIDE_MIN_COLUMNS:
                shown = ", ".join(siblings[:6]) + (" …" if len(siblings) > 6 else "")
                c.notes.append(
                    f"Kırılım kolon adlarına gömülü (geniş format): {lead.col.column}, "
                    f"{shown}. Toplam için ilgili kolonlar toplanmalı; tip/kanal satır "
                    "olarak isteniyorsa unpivot gerekir."
                )

    @staticmethod
    def _promote(c: FieldCandidate, f: ColumnFeatures) -> None:
        """Put the derivation's source column first in the listed fields."""
        hit = next((h for h in c.match.columns if h.col.id == f.col.id), None)
        hit = hit or ColumnHit(f.col, 0.0, 0.0, role="türetme")
        c.match.columns = [hit, *(h for h in c.match.columns if h is not hit)]

    @staticmethod
    def _status(
        cands: Sequence[FieldCandidate], min_answer: float, structural: bool
    ) -> FieldStatus:
        if not cands or cands[0].match.score < min_answer and not structural:
            return FieldStatus.NOT_FOUND
        best = cands[0]
        if structural:
            return FieldStatus.READY
        if best.derivation:
            return FieldStatus.DERIVE
        m = best.match
        # A scope limit (long-format values, "kapsam farkı", a term's "Kapsam:" note such as
        # virman = in-bank only) keeps any field at "Kısmen hazır".
        scope_limited = bool(m.long_format_values) or any(
            c.startswith("Kapsam") for c in m.columns[0].caveats
        )
        if scope_limited:
            return FieldStatus.PARTIAL
        if best.wide_family:
            # Ek A.3: the sum of the core table's per-channel columns counts as ready.
            return FieldStatus.READY
        if round(best.score, 2) >= READY_MIN and not best.notes:  # as displayed (%80)
            return FieldStatus.READY
        return FieldStatus.PARTIAL

    # ------------------------------------------------------------------ request level

    @staticmethod
    def _coverage(cores: Sequence[_Core], runs: Sequence[_FieldRun]) -> list[TableCoverage]:
        out = []
        for c in cores:
            scores = [run.matches[c.key].score for run in runs if c.key in run.matches]
            ready = sum(1 for s in scores if s >= READY_MIN)
            out.append(
                TableCoverage(
                    object_key=c.key,
                    object_name=c.key.rsplit(".", 1)[-1],
                    fields=c.served,
                    ready=ready,
                    partial=len(c.served) - ready,
                    mean_score=sum(scores) / len(runs) if runs else 0.0,
                )
            )
        return out

    def _notes(
        self,
        runs: Sequence[_FieldRun],
        results: Sequence[FieldResult],
        coverage: Sequence[TableCoverage],
        grain: str,
        grain_field: RequestField | None,
    ) -> list[Note]:
        notes: list[Note] = []
        engine = self.engine
        if coverage:
            core = coverage[0]
            notes.append(
                Note(
                    "Kapsam",
                    "Tek tablo kapsama",
                    f"{core.object_name}, talep edilen {len(results)} alanın {len(core.fields)} "
                    f"tanesini karşılayabiliyor ({core.ready} tanesi hazır düzeyde).",
                )
            )
            if grain:
                fit, col = self._time_fit(core.object_key, grain)
                where = f" ({grain_field.label} alanı)" if grain_field else ""
                if fit >= 0.8 and col is not None:
                    text = (
                        f"Talep {grain} düzeyde{where}; {core.object_name} bunu "
                        f"{col.col.column} ile karşılıyor."
                    )
                else:
                    text = (
                        f"Talep {grain} düzeyde{where}; {core.object_name} bu düzeyde bir "
                        "zaman kolonu taşımıyor. Daha ayrıntılı (işlem seviyesi) bir tablodan "
                        "toplulaştırma gerekebilir."
                    )
                notes.append(Note("Kapsam", "Zaman düzeyi", text))

            by_obj: dict[str, list[str]] = {}
            for r in results:
                if r.best is not None and r.best.match.object_key != core.object_key:
                    by_obj.setdefault(r.best.match.object_key, []).append(r.field.label)
            core_keys = set(engine.join_keys.get(core.object_key, []))
            for key, labels in by_obj.items():
                shared = [k for k in engine.join_keys.get(key, []) if k in core_keys]
                how = (
                    f"{' + '.join(shared)} üzerinden birleştirilebilir"
                    if shared
                    else "ortak anahtar bulunamadı; birleştirme veri ekibiyle netleştirilmeli"
                )
                notes.append(
                    Note(
                        "Kapsam",
                        f"Ek tablo: {key.rsplit('.', 1)[-1]}",
                        f"{', '.join(labels)} için; {core.object_name} ile {how}.",
                    )
                )

        q_all = engine.expander.expand(" ".join(run.query for run in runs))
        seen: set[str] = set()
        for n in clarification_notes(q_all, engine.clarifications):
            if n.text not in seen:
                seen.add(n.text)
                notes.append(n)
        for run, r in zip(runs, results, strict=True):
            if run.q.unknown_concepts and r.status is not FieldStatus.READY:
                unknown = ", ".join(f"“{c.label}”" for c in run.q.unknown_concepts)
                notes.append(
                    Note("Kapsam", f"{run.field.label}: sözlükte geçmeyen kavram", unknown)
                )
            if r.best:
                for text in r.best.notes:
                    notes.append(Note("Alan notu", r.field.label, text))
        return notes

    @staticmethod
    def _summary(
        results: Sequence[FieldResult], coverage: Sequence[TableCoverage]
    ) -> tuple[Verdict, str]:
        counts = {s: sum(1 for r in results if r.status is s) for s in FieldStatus}
        n = len(results)
        if counts[FieldStatus.NOT_FOUND] == n:
            return (
                Verdict.NOT_FOUND,
                "BULUNAMADI — Talep edilen alanların hiçbiri sözlükte karşılanamadı.",
            )
        verdict = Verdict.FOUND if counts[FieldStatus.READY] == n else Verdict.PARTIAL
        core = coverage[0] if coverage else None
        lead = (
            f"Çekirdek tablo {core.object_name}: talep edilen {n} alanın "
            f"{len(core.fields)} tanesini karşılayabiliyor. "
            if core
            else ""
        )
        tally = ", ".join(f"{counts[s]} {tr_lower(s.value)}" for s in FieldStatus if counts[s])
        return verdict, f"{verdict.value} — {lead}Alan durumu: {tally}."
