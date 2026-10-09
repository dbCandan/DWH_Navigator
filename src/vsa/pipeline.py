"""Orchestration: query -> search -> column rules -> object
aggregation -> validation -> explained result. Pure given its inputs; the
``Engine.from_*`` constructors are the only parts that touch files.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from vsa import cancel, dictionary_store, trace
from vsa.answer_cache import fingerprint, meaning_key, text_key
from vsa.config import Settings
from vsa.expansion.query_expander import Concept, ExpandedQuery, QueryExpander
from vsa.features import ColumnFeatures, build_features
from vsa.index.bm25 import BM25Index, weighted_fields
from vsa.index.store import load_index, save_index
from vsa.llm.analyst import (
    STRUCTURAL,
    AnalystAnswer,
    Catalog,
    MentionChecker,
    Recommendation,
    Shortlist,
    analyse,
    build_answer,
    build_catalog,
    column_caveats,
    confusable_material,
    narrow_tables,
    shortlist,
    table_material,
    term_matcher,
)
from vsa.llm.client import LLMClient, NullClient, client_from_settings
from vsa.loader import load_stopword_file, load_term_dictionary
from vsa.models import (
    AnalysisResult,
    ColumnHit,
    DictColumn,
    Dictionary,
    Note,
    ObjectMatch,
    TermGroup,
    Verdict,
)
from vsa.scoring.aggregate import ObjectColumns, aggregate
from vsa.scoring.combine import level_for
from vsa.scoring.explain import explain, key_columns, summary_sentence
from vsa.scoring.rules import covers, score_column
from vsa.scoring.topic import build_topic_index, topic_scores
from vsa.text.normalize import fold, tokenize
from vsa.validate import validate

log = logging.getLogger(__name__)

NEAR_MISS_COUNT = 3
# Rule results shown to the analyst model as hints (ADR-029).
ANALYST_HINT_TABLES = 15
ANALYST_RULE_POOL = 60  # rule-ranked tables the "together" hint picks from
ANALYST_HINT_COLUMNS = 25
FAMILY_MIN_SHARE = 0.6  # a family table must score this share of the family's best table


@dataclass(slots=True)
class Resources:
    """Everything the engine needs besides the dictionary itself."""

    term_groups: list[TermGroup] = field(default_factory=list)
    stopwords: frozenset[str] = frozenset()

    @classmethod
    def from_settings(cls, settings: Settings) -> Resources:
        term_path = Path(settings.expansion.term_dictionary)
        groups = load_term_dictionary(term_path) if term_path.exists() else []
        if not term_path.exists():
            log.warning("Terim sözlüğü bulunamadı: %s", term_path)
        return cls(groups, load_stopword_file(Path(settings.expansion.stopwords)))


@dataclass(slots=True)
class AnalystReading:
    """What the analyst model reads in step 2 (ADR-029)."""

    catalog: Catalog
    checker: MentionChecker
    ranked: list[ObjectMatch]  # rule ranking, shown as hints
    q: ExpandedQuery
    relevance: dict[int, float]
    short: Shortlist
    added: dict[str, str]  # tables added by family search -> family
    readable: list[str]  # candidates + added, in reading order
    material: str
    confusables: str
    columns_of: dict[str, list[DictColumn]]
    seconds: float  # step 1

    @property
    def ids(self) -> dict[str, str]:
        """Catalog ids the model may recommend -> object key."""
        return {self.catalog.keys[k]: k for k in self.readable}


class Engine:
    def __init__(
        self,
        dictionary: Dictionary,
        settings: Settings,
        resources: Resources,
        bm25: BM25Index | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.dictionary = dictionary
        self.settings = settings
        self.resources = resources
        self.llm: LLMClient = llm or NullClient()
        self.features = _features_for(dictionary, resources.stopwords)
        if [f.col.id for f in self.features] != list(range(len(self.features))):
            raise ValueError("Kolon id'leri 0..N-1 sıralı olmalı")

        by_obj: dict[str, list[ColumnFeatures]] = defaultdict(list)
        for f in self.features:
            by_obj[f.col.object_key].append(f)
        self.objects = {k: ObjectColumns(k, tuple(v)) for k, v in by_obj.items()}
        self.join_keys = {
            k: key_columns([f.col.column for f in o.features]) for k, o in self.objects.items()
        }
        self.column_keys = frozenset(c.key for c in dictionary.columns)
        self.topic_keys, self.topic_index = build_topic_index(
            {k: o.features for k, o in self.objects.items()},
            {
                k: tokenize(f"{p.description} {p.grain}", stopwords=resources.stopwords,
                            keep_compound=False)
                for k, p in dictionary.objects.items()
            },
        )  # fmt: skip
        self._df_cache: dict[Concept, int] = {}

        s = settings.search
        self.bm25 = bm25 or BM25Index.build(
            [weighted_fields(f) for f in self.features], s.field_weights, s.bm25.k1, s.bm25.b
        )
        self.expander = QueryExpander(
            resources.term_groups,
            self.features,
            resources.stopwords,
            expansion_weight=settings.expansion.weight,
            enabled=settings.expansion.enabled,
            use_synonyms=settings.expansion.synonyms,
        )

    # ------------------------------------------------------------------ construction

    @classmethod
    def from_dictionary_file(cls, settings: Settings) -> Engine:
        path = Path(settings.dictionary.store)
        dictionary = (
            dictionary_store.load_dictionary(path) if path.is_file()
            else dictionary_store.empty(path)
        )  # fmt: skip
        return cls(
            dictionary,
            settings,
            Resources.from_settings(settings),
            llm=client_from_settings(settings.llm),
        )

    @classmethod
    def from_index(cls, settings: Settings) -> Engine:
        dictionary, bm25, meta = load_index(Path(settings.index.dir))
        engine = cls(
            dictionary,
            settings,
            Resources.from_settings(settings),
            bm25=bm25,
            llm=client_from_settings(settings.llm),
        )
        engine.index_meta = meta
        return engine

    def cache_keys(self, query: str) -> tuple[str, str]:
        """(text key, meaning key) of a question for reusing earlier answers (ADR-035)."""
        return text_key(query), meaning_key(self.expander.expand(query))

    def cache_fingerprint(self, top_n: int) -> str:
        """What this engine's answers depend on besides the question (ADR-035)."""
        return fingerprint(
            self.settings,
            self.dictionary.version,
            self.resources.term_groups,
            top_n,
            self.resources.stopwords,
        )

    index_meta: dict[str, Any] = {}

    def save(self) -> dict[str, Any]:
        return save_index(Path(self.settings.index.dir), self.dictionary, self.bm25)

    # ------------------------------------------------------------------ analysis

    def rank_objects(
        self, query: str, *, limit: int | None = None
    ) -> tuple[list[ObjectMatch], ExpandedQuery]:
        """The rule engine's ranked objects for a query (no answer threshold): the
        analyst's hints (and the measured rule answer). ``limit`` overrides how many are kept."""
        s = self.settings
        lap = trace.Laps()
        lap("Sorgu genişletme")
        q = self.expander.expand(query)
        self._weigh_concepts(q)
        lap.note(f"{len(q.concepts)} kavram, {len(q.sparse_terms)} arama terimi")
        lap("BM25 arama")
        scored = self.bm25.search(q.sparse_terms, top_k=len(self.features))
        bm25_map = dict(scored)
        max_bm25 = scored[0][1] if scored else 0.0

        pool = {doc for doc, _ in scored[: s.search.candidate_object_columns]}
        pool |= set(q.synonym_hits)
        lap.note(f"{len(pool)} aday kolon")
        lap("Kolon skorlama")
        candidate_objects = {self.features[i].col.object_key for i in pool}
        hits: dict[int, ColumnHit] = {}
        for key in candidate_objects:
            for f in self.objects[key].features:
                hits[f.col.id] = score_column(
                    f,
                    bm25_map.get(f.col.id, 0.0),
                    max_bm25,
                    q,
                )
        lap.note(f"{len(candidate_objects)} tablonun {len(hits)} kolonu")
        lap("Tablo toplama ve konu uyumu")
        topic = (
            topic_scores(
                self.topic_keys,
                self.topic_index,
                q.sparse_terms,
                sorted(candidate_objects),
            )
            if s.scoring.object.topic > 0
            else None
        )
        ranked = aggregate(
            hits,
            q,
            {k: self.objects[k] for k in candidate_objects},
            s.scoring.object,
            s.scoring.min_candidate_score,
            topic,
        )
        if limit is None:
            limit = s.search.top_k_objects + NEAR_MISS_COUNT
        kept = [
            m
            for i, m in enumerate(ranked)
            if i < limit and m.score >= s.scoring.min_candidate_score
        ]
        lap.note(f"{len(kept)} tablo eşik üstünde")
        lap.done()
        return kept, q

    def _concept_df(self, concept: Concept) -> int:
        if concept not in self._df_cache:
            self._df_cache[concept] = sum(1 for f in self.features if covers(f.all_tokens, concept))
        return self._df_cache[concept]

    def _weigh_concepts(self, q: ExpandedQuery) -> None:
        """IDF weight per content concept; concepts found nowhere are recorded (ADR-013)."""
        n = len(self.features)
        for c in q.content_concepts:
            df = self._concept_df(c)
            q.concept_weights[c] = math.log(1 + n / (df + 1))
            if df == 0:
                q.unknown_concepts.append(c)

    @property
    def analyst_enabled(self) -> bool:
        """A chat model is connected: the analyst writes the answer (ADR-029)."""
        return self.llm.available

    def analyze(self, query: str, top_n: int = 5) -> AnalysisResult:
        """The one question flow: the analyst writes every answer (ADR-029, ADR-038). With
        no model, a dead server or a failed analysis the result says why and lists nothing;
        there is no rule answer to fall back to."""
        if not self.dictionary.columns:
            return self._unavailable(
                query, "Sözlük henüz içe aktarılmadı; Yönetim → Sözlük ekranından şablondaki "
                "Excel'i içe aktarın.",
            )  # fmt: skip
        if not self.analyst_enabled:
            return self._unavailable(
                query, "Sohbet modeli bağlı değil; Yönetim → Yapay zekâ sayfasından "
                "bir model bağlayın.",
            )  # fmt: skip
        with trace.span("Model sunucusu kontrolü", self.llm.model) as s:
            down = self.llm.health()
            if s is not None and down:
                s.status, s.detail = "error", down
        if down:  # do not wait on a dead server: say so at once
            reason = down if "ulaşılamadı" in down else f"Model sunucusu yanıt vermedi: {down}"
            return self._unavailable(query, reason)
        with trace.span("Analist akışı", self.llm.model) as s:
            result = self._analyze_llm(query, top_n)
            if s is not None and result is None:
                s.status = "error"
        if result is not None:
            return result
        cancel.check()  # a stopped analysis ends here
        log.warning("Analist akışı sonuç veremedi")
        return self._unavailable(
            query, fallback_reason(str(getattr(self.llm, "last_error", "")))
        )

    def _unavailable(self, query: str, reason: str) -> AnalysisResult:
        """The answer when the analyst could not run: no tables, and the reason."""
        trace.event("Analiz yapılamadı", reason)
        return AnalysisResult(
            query=query,
            verdict=Verdict.NOT_FOUND,
            summary=f"Analiz yapılamadı: {reason}",
            objects=[],
            near_misses=[],
            notes=[],
            concepts=[],
            expansion_terms=[],
            dictionary_source=Path(self.dictionary.source_path).name,
            dictionary_version=self.dictionary.version,
            dictionary_objects=len(self.objects),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            method=["Analiz yapılamadı — cevabı yalnız analist (sohbet modeli) yazar (ADR-038)"],
            llm_model=self.llm.model if self.analyst_enabled else "",
            fallback=reason,
        )

    # ------------------------------------------------------------------ analyst (ADR-029)

    _catalog: Catalog | None = None
    _checker: MentionChecker | None = None

    def _analyst_parts(self) -> tuple[Catalog, MentionChecker]:
        if self._catalog is None or self._checker is None:
            self._catalog = build_catalog(
                {k: [f.col for f in o.features] for k, o in self.objects.items()},
                self.dictionary.objects,
            )
            self._checker = MentionChecker.build(self.dictionary.columns)
        return self._catalog, self._checker

    def _column_relevance(self, q: ExpandedQuery) -> dict[int, float]:
        """BM25 score of every matching column, scaled to 0..1."""
        scored = self.bm25.search(q.sparse_terms, top_k=len(self.features))
        top = scored[0][1] if scored else 0.0
        return {i: v / top for i, v in scored if top > 0 and v > 0}

    def _hints(
        self, ranked: Sequence[ObjectMatch], relevance: Mapping[int, float], catalog: Catalog
    ) -> str:
        def line(m: ObjectMatch) -> str:
            concepts = ", ".join(m.covered) or "-"
            return f"- {catalog.keys[m.object_key]} {m.object_key} (kavramlar: {concepts})"

        lines = ["Kural skoru en yüksek tablolar:"]
        lines += [line(m) for m in ranked[:ANALYST_HINT_TABLES]]
        # ADR-005: a table carrying the requested concepts together beats a join.
        together = sorted(ranked, key=lambda m: (-len(m.covered), -m.score))
        lines.append("Talebin kavramlarını en çok BİRLİKTE taşıyan tablolar:")
        lines += [line(m) for m in together[:ANALYST_HINT_TABLES] if len(m.covered) > 1]
        best = sorted(relevance, key=lambda i: -relevance[i])[:ANALYST_HINT_COLUMNS]
        lines.append("Kelime eşleşmesi en güçlü kolonlar:")
        lines += [f"- {self.features[i].col.key}" for i in best]
        return "\n".join(lines)

    def analyst_read(self, query: str) -> AnalystReading | None:
        """Step 1 of the analyst flow and the material for step 2 (ADR-029): the model
        picks candidates from the catalog, family search adds tables it overlooked, and
        every readable table is laid out with its columns, descriptions and concept
        evidence. None when the model fails (the caller reports why, ADR-038)."""
        a = self.settings.analyst
        catalog, checker = self._analyst_parts()
        with trace.span("Kural motoru ipuçları"):
            ranked, q = self.rank_objects(query, limit=ANALYST_RULE_POOL)
            relevance = self._column_relevance(q)
        started = time.perf_counter()
        with trace.span("1. adım — aday seçimi", f"{len(catalog.ids)} tablonun kataloğu") as sp:
            hints = self._hints(ranked, relevance, catalog)
            short = shortlist(query, catalog, hints, self.llm, a.shortlist)
            if sp is not None and short is None:
                sp.status, sp.detail = "error", "yanıt yok"
            elif sp is not None and short is not None:
                sp.detail = f"{len(short.candidates)} aday, {len(short.confusables)} benzer tablo"
        if short is None:
            return None
        seconds = time.perf_counter() - started
        columns_of = {k: [f.col for f in o.features] for k, o in self.objects.items()}
        with trace.span("Aile araması") as sp:
            added = self._family_tables(short) if short.candidates else {}
            by_search = (
                self._searched_tables(q, {*short.candidates, *short.confusables, *added})
                if short.candidates  # "bulunamadı" from step 1 stays one call
                else {}
            )
            added |= by_search
            if sp is not None:
                sp.detail = f"{len(added)} tablo eklendi"
        readable = [*short.candidates, *added]
        material = confusables = ""
        if readable:
            terms = [*short.search_terms, *(w for _, words in short.families for w in words)]
            hits = term_matcher(terms)
            rel = {
                c.id: relevance.get(c.id, 0.0) + 0.5 * hits(c)
                for k in readable
                for c in columns_of[k]
            }
            material = "\n\n".join(
                table_material(
                    k,
                    catalog.keys[k],
                    columns_of[k],
                    rel,
                    a.description_chars,
                    a.full_table_columns,
                    self._concept_evidence(k, q, rel)
                    + ("\nTablo aramasıyla eklendi (1. adımda seçilmedi)" if k in by_search
                       else f"\nAile aramasıyla eklendi: {added[k]}" if k in added else ""),
                    detail_columns=a.detail_columns,
                    profile=self.dictionary.objects.get(k),
                )  # fmt: skip
                for k in readable
            )
            confusables = confusable_material(
                self.dictionary.columns, readable, short.confusables[: a.confusables],
                relevance, short.search_terms, a.evidence_columns,
            )  # fmt: skip
        return AnalystReading(
            catalog, checker, ranked, q, relevance, short, added, readable, material,
            confusables, columns_of, seconds,
        )  # fmt: skip

    _narrow_keys: frozenset[str] | None = None

    def _narrow(self) -> frozenset[str]:
        if self._narrow_keys is None:
            self._narrow_keys = narrow_tables(
                {k: p.description for k, p in self.dictionary.objects.items()}
            )
        return self._narrow_keys

    def _analyze_llm(self, query: str, top_n: int) -> AnalysisResult | None:
        started = time.perf_counter()
        a = self.settings.analyst
        reading = self.analyst_read(query)
        if reading is None:
            return None
        catalog, checker, ranked, q = reading.catalog, reading.checker, reading.ranked, reading.q
        relevance, short, added = reading.relevance, reading.short, reading.added
        readable, columns_of = reading.readable, reading.columns_of
        t2 = time.perf_counter()
        answer: AnalystAnswer
        if readable:
            n_columns = sum(len(columns_of[k]) for k in readable)
            with trace.span("2. adım — kolon okuma ve rapor",
                            f"{len(readable)} tablo, {n_columns} kolon") as sp:  # fmt: skip
                reply = analyse(query, short.interpretation, reading.material,
                                reading.confusables, self.llm, top_n, a.max_tokens)  # fmt: skip
                if sp is not None and reply is None:
                    sp.status = "error"
            if reply is None:
                return None
            answer = build_answer(
                reply, reading.ids, columns_of, checker, top_n, a.min_confidence, catalog.ids,
                self._narrow(),
            )
        else:
            answer = AnalystAnswer(
                Verdict.NOT_FOUND,
                "BULUNAMADI. Veri ambarı kataloğunda bu talebi karşılayan bir tablo bulunamadı.",
                [], [], [], [],
            )  # fmt: skip
        t3 = time.perf_counter()

        rules = {m.object_key: m for m in ranked}
        warnings = [*answer.attention, *(n.text for n in answer.notes)]
        objects = [self.recommended_match(r, rules.get(r.object_key), relevance, warnings)
                   for r in answer.recommendations]  # fmt: skip
        notes = list(answer.notes)
        dropped = answer.dropped + short.unknown_ids
        notes.append(
            Note(
                "Genel",
                "Doğrulama",
                "Önerilen tüm tablo ve alanlar veri sözlüğüne karşı doğrulandı"
                + (
                    f"; sözlükte karşılığı olmayan {dropped} ad/cümle rapordan çıkarıldı"
                    if dropped
                    else ""
                )  # fmt: skip
                + ". Skorlar sözlük tanımlarına dayanır; kullanım öncesinde ilgili tablolarda "
                "veri doluluğu, güncellik ve erişim yetkileri kontrol edilmelidir.",
            )
        )
        method = [
            f"Analist akışı (ADR-029): {self.llm.model}",
            f"1. adım — {len(catalog.ids)} tablonun kataloğundan {len(short.candidates)} aday "
            f"ve {len(short.confusables)} benzer tablo seçildi ({reading.seconds:.0f} sn)",
            "Okunan adaylar: " + (", ".join(k.rsplit(".", 1)[-1] for k in short.candidates) or "-"),
            "Benzer (uyarı) tablolar: "
            + (", ".join(k.rsplit(".", 1)[-1] for k in short.confusables) or "-"),
            "Aile aramasıyla eklenen: "
            + (", ".join(f"{k.rsplit('.', 1)[-1]} ({f})" for k, f in added.items()) or "-"),
            f"2. adım — adayların {sum(len(columns_of[k]) for k in readable)} kolonu "
            f"sözlük açıklamalarıyla okundu, rapor yazıldı ({t3 - t2:.0f} sn)",
            "Arama motoru (BM25) sonuçları modele ipucu ve benzer alan kanıtı olarak verildi",
            "Güven skoru: analist değerlendirmesi; kural skoru Ayrıntılar'da gösterilir",
            f"Sözlük doğrulaması: {dropped} ad/cümle düşürüldü",
        ]
        return AnalysisResult(
            query=query,
            verdict=answer.verdict,
            summary=answer.summary,
            objects=objects,
            near_misses=[],
            notes=notes,
            concepts=[c.display() for c in q.concepts],
            expansion_terms=q.expansion_terms,
            dictionary_source=Path(self.dictionary.source_path).name,
            dictionary_version=self.dictionary.version,
            dictionary_objects=len(self.objects),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            method=method,
            dropped_by_validation=dropped,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            llm_model=self.llm.model,
            interpretation=short.interpretation,
            design=answer.design,
            attention=answer.attention,
            analyst=True,
            missing=answer.missing,
        )

    def _family_tables(self, short: Shortlist) -> dict[str, str]:
        """Tables the model did not pick but whose names / columns / descriptions carry
        one of the request's information families (table-level BM25 over the family's
        terms, ADR-029). Returns object key -> family name."""
        a = self.settings.analyst
        taken = {*short.candidates, *short.confusables}
        added: dict[str, str] = {}
        for name, words in short.families:
            query = {
                tok: 1.0 for w in words for tok in tokenize(w, stopwords=self.resources.stopwords)
            }
            if not query:
                continue
            found = 0
            results = self.topic_index.search(query, top_k=a.family_tables * 4)
            top = results[0][1] if results else 0.0
            for doc, score in results:
                if score < FAMILY_MIN_SHARE * top:
                    break  # weak lexical matches only add noise (a safe-box table for card limits)
                key = self.topic_keys[doc]
                if key in taken or key in added:
                    continue
                added[key] = name
                found += 1
                if found >= a.family_tables or len(added) >= a.family_extra:
                    break
            if len(added) >= a.family_extra:
                break
        return added

    def _searched_tables(self, q: ExpandedQuery, taken: set[str]) -> dict[str, str]:
        """The table-level word search's best tables (profiles included) that step 1 did
        not pick, read in step 2 as a safety net — the oracles' "search once more" habit,
        done cheaply. Returns object key -> "arama"."""
        n = self.settings.analyst.search_tables
        if n <= 0:
            return {}
        added: dict[str, str] = {}
        for doc, _ in self.topic_index.search(q.sparse_terms, top_k=n + len(taken)):
            key = self.topic_keys[doc]
            if key not in taken:
                added[key] = "arama"
                if len(added) >= n:
                    break
        return added

    def _concept_evidence(self, key: str, q: ExpandedQuery, relevance: Mapping[int, float]) -> str:
        """Which request concepts the table carries, and in which column (lexical)."""
        parts: list[str] = []
        for concept in q.content_concepts:
            carriers = [f for f in self.objects[key].features if covers(f.all_tokens, concept)]
            if carriers:
                best = max(carriers, key=lambda f: relevance.get(f.col.id, 0.0))
                parts.append(f"{concept.label} ✓ {best.col.column}")
            else:
                parts.append(f"{concept.label} ✗")
        return ("Talep kavramları (kelime eşleşmesi): " + " · ".join(parts)) if parts else ""

    def recommended_match(
        self,
        r: Recommendation,
        rule: ObjectMatch | None,
        relevance: Mapping[int, float],
        warnings: Sequence[str] = (),
    ) -> ObjectMatch:
        feats = self.objects[r.object_key].features
        first = feats[0].col
        hits = [
            ColumnHit(
                col=c,
                rule_score=relevance.get(c.id, 0.0),
                role="yapısal" if fold(c.column) in STRUCTURAL else "eşleşme",
                caveats=column_caveats(c.column, [r.caveat, *warnings]),
            )
            for c in r.columns
        ]
        return ObjectMatch(
            object_key=r.object_key,
            database=first.database,
            schema=first.schema,
            object_name=first.object_name,
            dataset_groups=sorted({f.col.dataset_group for f in feats if f.col.dataset_group}),
            score=r.confidence,
            level=level_for(r.confidence),
            columns=hits,
            components=dict(rule.components) if rule else {},
            covered=list(rule.covered) if rule else [],
            missing=[],
            reason=r.reason,
            caveat=r.caveat,
            usage=r.usage,
            rule_score=rule.score if rule else None,
            llm_confidence=r.confidence,
            covers=r.covers,
        )

    # ------------------------------------------------------------------ rules

    def rule_answer(self, query: str, top_n: int = 5) -> AnalysisResult:
        """The rule engine's own answer. Never shown to users (ADR-038); kept to measure
        the hints the analyst gets (`vsa eval` without a model, regression tests)."""
        started = time.perf_counter()
        s = self.settings
        ranked, q = self.rank_objects(query)
        ranked, dropped = validate(ranked, self.column_keys)

        top = ranked[:top_n]
        near = ranked[top_n : top_n + NEAR_MISS_COUNT]
        found = bool(top) and top[0].score >= s.scoring.min_answer_score and (
            top[0].components.get("coverage", 1.0) >= s.scoring.min_answer_coverage)  # fmt: skip
        # Without the analyst the ranking is word and meaning matching only (ADR-034): the
        # confidence shown is the rule score times a factor; "bulunamadı" stays on the raw score.
        factor = s.scoring.rule_only_factor
        for m in ranked:
            m.rule_score = m.score
            m.score = round(m.score * factor, 4)
            m.level = level_for(m.score)
        if not found:
            verdict = Verdict.NOT_FOUND
            near, top = top[:NEAR_MISS_COUNT], []
        elif top[0].level.value == "Yüksek" and not top[0].missing:
            verdict = Verdict.FOUND
        else:
            verdict = Verdict.PARTIAL
        for m in (*top, *near):
            explain(m, q)

        notes: list[Note] = []
        if q.unknown_concepts:
            labels = ", ".join(f"“{c.label}”" for c in q.unknown_concepts)
            notes.append(
                Note(
                    "Kapsam",
                    "Sözlükte hiç geçmeyen kavram",
                    f"{labels} sözlüğün hiçbir kolonunda geçmiyor. Veri ambarında bu kavram "
                    "yok ya da farklı bir terimle adlandırılıyor olabilir; terim sözlüğüne "
                    "eklenmesi değerlendirilmeli.",
                )
            )
        for m in near:
            notes.append(
                Note(
                    "Yakın aday",
                    m.object_key,
                    f"Güven %{round(m.score * 100)} — {m.reason}",
                )
            )
        notes.append(
            Note(
                "Doğrulama",
                "Sözlük doğrulaması",
                "Önerilen tüm alanlar sözlükte doğrulandı."
                if dropped == 0
                else f"Sözlükte bulunamayan {dropped} alan rapordan çıkarıldı.",
            )
        )

        method = [
            "Arama: alan ağırlıklı BM25 (kolon adı ×3, eş anlamlılar ×2, açıklama ×1, obje ×1)",
            "Sorgu genişletme: kurumsal terim sözlüğü + sözlük içi eş anlamlılar",
            "Skorlama: kural tabanlı; tablo seviyesinde en iyi kolon + kapsama + zaman "
            "+ granülerlik + konu uyumu",
            "Model: kullanılmadı — cevabı kural motoru üretti",
            f"Güven skorları: kural skoru × {factor:g} (analist olmadan daha az isabetli; ADR-034)",
        ]
        return AnalysisResult(
            query=query,
            verdict=verdict,
            summary=summary_sentence(verdict, top),
            objects=top,
            near_misses=near,
            notes=notes,
            concepts=[c.display() for c in q.concepts],
            expansion_terms=q.expansion_terms,
            dictionary_source=Path(self.dictionary.source_path).name,
            dictionary_version=self.dictionary.version,
            dictionary_objects=len(self.objects),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            method=method,
            dropped_by_validation=dropped,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            confidence_factor=factor,
        )


# Tokenizing 11k column texts is ~95% of building an engine (~3 s). Every settings change
# rebuilds the engine with the same dictionary, so the features are kept per content.
_FEATURES: dict[int, list[ColumnFeatures]] = {}
_FEATURES_KEPT = 2  # the app's dictionary, and a restricted one during `vsa eval`


def _features_for(dictionary: Dictionary, stopwords: frozenset[str]) -> list[ColumnFeatures]:
    key = hash((stopwords, tuple((c.id, c.key, c.description, c.synonyms)
                                 for c in dictionary.columns)))  # fmt: skip
    if key not in _FEATURES:
        while len(_FEATURES) >= _FEATURES_KEPT:
            _FEATURES.pop(next(iter(_FEATURES)))
        _FEATURES[key] = [build_features(c, stopwords) for c in dictionary.columns]
    return _FEATURES[key]


def fallback_reason(error: str) -> str:
    """Plain Turkish reason for an analyst failure, from the model server's error text."""
    text = fold(error)
    if "context" in text and ("exceed" in text or "size" in text or "length" in text):
        return (
            "Modelin bağlam penceresi tablo kataloğu için küçük (~70k token gerekir). Model "
            "sunucusunda daha geniş bağlam açın (vLLM: --max-model-len) veya Yönetim → "
            "Yapay zekâ'dan daha geniş bağlamlı bir sohbet modeli seçin."
        )
    if "timed out" in text or "timeout" in text or "504" in text:
        return "Model zamanında yanıt vermedi (zaman aşımı)."
    if "connection" in text or "ulasilamadi" in text or "refused" in text:
        return "Model sunucusuna ulaşılamadı."
    return f"Model hatası: {error[:160]}" if error else "Model yanıt vermedi."
