"""Orchestration (HANDOVER §4): query -> search -> column rules -> object
aggregation -> validation -> explained result. Pure given its inputs; the
``Engine.from_*`` constructors are the only parts that touch files.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from vsa import trace
from vsa.config import Settings
from vsa.expansion.query_expander import (
    Concept,
    ExpandedQuery,
    QueryExpander,
    build_synonym_index,
)
from vsa.features import ColumnFeatures, build_features
from vsa.index.bm25 import BM25Index, weighted_fields
from vsa.index.dense import (
    DenseIndex,
    ObjectDenseIndex,
    load_dense_index,
    load_object_index,
    normalize,
)
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
    chunk_catalog,
    column_caveats,
    confusable_material,
    read_chunks,
    reconcile,
    shortlist,
    table_material,
    term_matcher,
)
from vsa.llm.client import LLMClient, LLMError, NullClient, client_from_settings
from vsa.llm.judge import JudgeResult, judge
from vsa.llm.prompts import EXPAND_SCHEMA, EXPAND_SYSTEM, expand_user
from vsa.loader import load_dictionary, load_stopword_file, load_term_dictionary
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
from vsa.scoring.combine import combine, level_for
from vsa.scoring.explain import (
    Clarification,
    apply_llm_texts,
    clarification_notes,
    compile_clarifications,
    explain,
    join_suggestions,
    key_columns,
    quality_notes,
    summary_sentence,
)
from vsa.scoring.rules import covers, score_column
from vsa.scoring.topic import build_topic_index, topic_scores
from vsa.text.normalize import fold, tokenize
from vsa.validate import validate

log = logging.getLogger(__name__)

CLARIFICATIONS_PATH = Path("config/clarifications.yaml")
NEAR_MISS_COUNT = 3
# Tables most similar to the request by their profile vector join the candidate pool
# even when none of their columns did (ADR-028).
OBJECT_POOL = 15
# Rule results shown to the analyst model as hints (ADR-029).
ANALYST_HINT_TABLES = 15
ANALYST_RULE_POOL = 60  # rule-ranked tables the "together" hint picks from
POOL_RULE_TOGETHER = 8  # rule tables carrying most request concepts, added to the pool
POOL_RULE_TOP = 5  # and the rule ranking's first ones
ANALYST_HINT_COLUMNS = 25


@dataclass(slots=True)
class Resources:
    """Everything the engine needs besides the dictionary itself."""

    term_groups: list[TermGroup] = field(default_factory=list)
    stopwords: frozenset[str] = frozenset()
    clarifications: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_settings(cls, settings: Settings) -> Resources:
        term_path = Path(settings.expansion.term_dictionary)
        groups = load_term_dictionary(term_path) if term_path.exists() else []
        if not term_path.exists():
            log.warning("Terim sözlüğü bulunamadı: %s", term_path)
        clar: list[dict[str, Any]] = []
        if CLARIFICATIONS_PATH.exists():
            clar = yaml.safe_load(CLARIFICATIONS_PATH.read_text(encoding="utf-8")) or []
        return cls(groups, load_stopword_file(Path(settings.expansion.stopwords)), clar)


@dataclass(slots=True)
class AnalystReading:
    """What the analyst model reads in step 2 (ADR-029), shared by ``ask`` and batch."""

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
    steps: list[str] = field(default_factory=list)  # how step 1 went, for the method notes

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
        dense: DenseIndex | None = None,
    ) -> None:
        self.dictionary = dictionary
        self.settings = settings
        self.resources = resources
        self.llm: LLMClient = llm or NullClient()
        self.dense = dense
        self.object_dense: ObjectDenseIndex | None = None
        self._qvec_cache: dict[str, np.ndarray] = {}
        self._expand_cache: dict[str, list[str]] = {}
        self._dense_error = ""
        self.features = [build_features(c, resources.stopwords) for c in dictionary.columns]
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
            {k: o.features for k, o in self.objects.items()}
        )
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
        self.clarifications: list[Clarification] = compile_clarifications(
            resources.clarifications, resources.stopwords
        )

    # ------------------------------------------------------------------ construction

    @classmethod
    def from_dictionary_file(cls, settings: Settings) -> Engine:
        d = settings.dictionary
        dictionary = load_dictionary(Path(d.path), d.sheet, d.quality_sheet)
        engine = cls(
            dictionary,
            settings,
            Resources.from_settings(settings),
            llm=client_from_settings(
                settings.llm, embeddings=settings.dense.enabled, cloud=settings.cloud
            ),
            dense=_dense_for(settings, len(dictionary.columns)),
        )
        engine.object_dense = _object_dense_for(settings, engine.objects)
        return engine

    @classmethod
    def from_index(cls, settings: Settings) -> Engine:
        dictionary, bm25, meta = load_index(Path(settings.index.dir))
        engine = cls(
            dictionary,
            settings,
            Resources.from_settings(settings),
            bm25=bm25,
            llm=client_from_settings(
                settings.llm, embeddings=settings.dense.enabled, cloud=settings.cloud
            ),
            dense=_dense_for(settings, len(dictionary.columns)),
        )
        engine.object_dense = _object_dense_for(settings, engine.objects)
        engine.index_meta = meta
        return engine

    @property
    def hybrid(self) -> bool:
        """Dense arm active: index loaded and the embedding model reachable so far."""
        return self.dense is not None and not self._dense_error

    def _query_vector(self, text: str) -> np.ndarray | None:
        if not self.hybrid:
            return None
        if text not in self._qvec_cache:
            try:
                vec = np.asarray(self.llm.embed([text])[0], dtype=np.float32)
            except LLMError as exc:
                self._dense_error = str(exc)
                log.warning("Vektör araması devre dışı, yalnız BM25 ile devam: %s", exc)
                return None
            self._qvec_cache[text] = normalize(vec)
        return self._qvec_cache[text]

    index_meta: dict[str, Any] = {}

    def save(self) -> dict[str, Any]:
        s = self.settings
        return save_index(
            Path(s.index.dir),
            self.dictionary,
            self.bm25,
            build_synonym_index(self.features),
            {"field_weights": s.search.field_weights, "k1": s.search.bm25.k1, "b": s.search.bm25.b},
        )

    # ------------------------------------------------------------------ analysis

    def rank_objects(
        self,
        query: str,
        include: Iterable[str] = (),
        *,
        use_llm: bool = True,
        limit: int | None = None,
        topic_fit: bool = True,
    ) -> tuple[list[ObjectMatch], ExpandedQuery]:
        """Ranked objects for a query (no answer threshold). Objects in ``include`` are
        always scored and kept, even when search alone would not reach them — batch
        mode uses this to judge every field against the core table. ``use_llm=False``
        skips the chat model (LLM query expansion); embeddings still run. ``limit``
        overrides how many objects are returned. ``topic_fit=False`` leaves out the
        table-level topic component (ADR-028); batch mode scores fields, not tables."""
        s = self.settings
        lap = trace.Laps()
        lap("Sorgu genişletme")
        q = self.expander.expand(query)
        self._weigh_concepts(q)
        if use_llm:
            self._llm_expand(q)
        lap.note(f"{len(q.concepts)} kavram, {len(q.sparse_terms)} arama terimi")
        lap("BM25 arama")
        scored = self.bm25.search(q.sparse_terms, top_k=len(self.features))
        bm25_map = dict(scored)
        max_bm25 = scored[0][1] if scored else 0.0

        pool = {doc for doc, _ in scored[: s.search.candidate_object_columns]}
        pool |= set(q.synonym_hits)
        lap.note(f"{len(pool)} aday kolon")
        if s.dense.enabled and self.hybrid:
            lap("Anlamsal arama")

        # M3: the dense arm uses the original wording (ADR-004) and widens the pool with
        # semantically close columns that share no words with the request.
        qvec = self._query_vector(q.dense_text) if s.dense.enabled else None
        dense_lo = dense_hi = 0.0
        if qvec is not None and self.dense is not None:
            dense_top = self.dense.search(qvec, s.dense.top_k)
            pool |= {i for i, _ in dense_top}
            dense_hi, dense_lo = dense_top[0][1], dense_top[-1][1]

        lap("Kolon skorlama")
        forced = {k for k in include if k in self.objects}
        candidate_objects = {self.features[i].col.object_key for i in pool} | forced
        object_sim: dict[str, float] | None = None
        if qvec is not None and self.object_dense is not None:
            object_sim = self.object_dense.similarity(qvec)
            if topic_fit:
                best = sorted(object_sim, key=lambda k: -object_sim[k])[:OBJECT_POOL]
                candidate_objects |= set(best)

        dense_sim: dict[int, float] = {}
        if qvec is not None and self.dense is not None and dense_hi > dense_lo:
            ids = [f.col.id for k in candidate_objects for f in self.objects[k].features]
            span = dense_hi - dense_lo
            raw = self.dense.similarity(qvec, ids)
            dense_sim = {i: max(0.0, min(1.0, (v - dense_lo) / span)) for i, v in raw.items()}

        hits: dict[int, ColumnHit] = {}
        for key in candidate_objects:
            for f in self.objects[key].features:
                hits[f.col.id] = score_column(
                    f,
                    bm25_map.get(f.col.id, 0.0),
                    max_bm25,
                    q,
                    s.scoring.flag_penalty,
                    dense=dense_sim.get(f.col.id) if dense_sim else None,
                    dense_weight=s.dense.weight if dense_sim else 0.0,
                )
        lap.note(f"{len(candidate_objects)} tablonun {len(hits)} kolonu")
        lap("Tablo toplama ve konu uyumu")
        topic = (
            topic_scores(
                self.topic_keys,
                self.topic_index,
                q.sparse_terms,
                sorted(candidate_objects),
                {k: self.objects[k].features for k in candidate_objects},
                dense_sim or None,
                object_sim,
            )
            if topic_fit and s.scoring.object.topic > 0
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
            if m.object_key in forced or (i < limit and m.score >= s.scoring.min_candidate_score)
        ]
        lap.note(f"{len(kept)} tablo eşik üstünde")
        lap.done()
        return kept, q

    def rank(
        self, query: str, include: Iterable[str] = ()
    ) -> tuple[list[ObjectMatch], ExpandedQuery, JudgeResult | None]:
        """``rank_objects`` plus the LLM judge on the top candidates when enabled."""
        ranked, q = self.rank_objects(query, include)
        verdict = self._judge(query, ranked)
        return ranked, q, verdict

    @property
    def judge_enabled(self) -> bool:
        return self.llm.available and self.settings.llm.judge

    def _judge(self, query: str, ranked: list[ObjectMatch]) -> JudgeResult | None:
        """Re-score with the judge (ADR-003): final = w_rule × rule + w_llm × llm, where
        objects the judge did not pick or did not see get llm = 0."""
        if not self.judge_enabled or not ranked:
            return None
        s = self.settings
        top = ranked[: s.llm.judge_candidates]
        with trace.span("LLM hakem", f"ilk {len(top)} aday"):
            result = judge(query, top, self.llm)
        if result is None:
            return None  # LLM failure -> rule result stands (ADR-008)
        for m in ranked:
            v = result.verdicts.get(m.object_key)
            m.rule_score = m.score
            m.llm_confidence = v.confidence if v else 0.0
            m.score = combine(m.score, m.llm_confidence, s.scoring.w_rule, s.scoring.w_llm)
            m.level = level_for(m.score)
            if v:
                m.llm_reason, m.llm_caveat, m.llm_usage = v.reason, v.caveat, v.usage
        ranked.sort(key=lambda m: (-m.score, m.object_key))
        return result

    def _llm_expand(self, q: ExpandedQuery) -> None:
        """§7.2c: model-generated terms only widen the BM25 pool (weight 0.6); they never
        become concepts or signals, so a misread concept cannot steer the score."""
        s = self.settings
        if not (s.llm.expand_query and self.llm.available):
            return
        if q.text not in self._expand_cache:
            reply = self.llm.chat_json(
                EXPAND_SYSTEM, expand_user(q.text), EXPAND_SCHEMA, max_tokens=400
            )
            terms: list[str] = []
            if reply:
                for key in ("synonyms_tr", "terms_en", "column_name_guesses"):
                    terms += [str(t) for t in reply.get(key, []) or [] if str(t).strip()][:8]
            self._expand_cache[q.text] = terms
        for term in self._expand_cache[q.text]:
            for tok in tokenize(term, stopwords=self.resources.stopwords):
                q.sparse_terms.setdefault(tok, s.expansion.weight)

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
        return self.llm.available and self.settings.analyst.enabled

    def analyze(self, query: str, top_n: int = 5) -> AnalysisResult:
        """Analyst flow when the chat model is on (ADR-029); rule pipeline otherwise and
        whenever the model fails (ADR-008)."""
        if self.analyst_enabled:
            with trace.span("Analist akışı", self.llm.model) as s:
                result = self._analyze_llm(query, top_n)
                if s is not None and result is None:
                    s.status = "error"
            if result is not None:
                return result
            log.warning("Analist akışı sonuç veremedi; kural tabanlı sonuca dönülüyor")
            return self._rules_after_failure(query, top_n)
        with trace.span("Kural akışı"):
            return self._analyze_rules(query, top_n)

    def _rules_after_failure(self, query: str, top_n: int) -> AnalysisResult:
        """Rule answer that says the analyst could not run, and why (ADR-008)."""
        reason = fallback_reason(str(getattr(self.llm, "last_error", "")))
        trace.event("Kural motoruna dönüldü", reason)
        with trace.span("Kural akışı (yedek)"):
            result = self._analyze_rules(query, top_n)
        result.fallback = reason
        return result

    # ------------------------------------------------------------------ analyst (ADR-029)

    _catalog: Catalog | None = None
    _checker: MentionChecker | None = None

    def _analyst_parts(self) -> tuple[Catalog, MentionChecker]:
        if self._catalog is None or self._checker is None:
            self._catalog = build_catalog(
                {k: [f.col for f in o.features] for k, o in self.objects.items()}
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
        # §8 / ADR-005: a table carrying the requested concepts together beats a join.
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
        evidence. None when the model fails (the caller falls back to rules)."""
        a = self.settings.analyst
        catalog, checker = self._analyst_parts()
        with trace.span("Kural motoru ipuçları"):
            ranked, q = self.rank_objects(query, use_llm=False, limit=ANALYST_RULE_POOL)
            relevance = self._column_relevance(q)
        started = time.perf_counter()
        steps: list[str] = []
        with trace.span("1. adım — aday seçimi", f"{len(catalog.ids)} tablonun kataloğu") as sp:
            if a.catalog_chunks > 1:
                short = self._split_shortlist(query, catalog, ranked, relevance, steps)
            else:
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
                    + (f"\nAile aramasıyla eklendi: {added[k]}" if k in added else ""),
                )  # fmt: skip
                for k in readable
            )
            confusables = confusable_material(
                self.dictionary.columns, readable, short.confusables[: a.confusables],
                relevance, short.search_terms, a.evidence_columns,
            )  # fmt: skip
        return AnalystReading(
            catalog, checker, ranked, q, relevance, short, added, readable, material,
            confusables, columns_of, seconds, steps,
        )  # fmt: skip

    def _split_shortlist(
        self,
        query: str,
        catalog: Catalog,
        ranked: Sequence[ObjectMatch],
        relevance: Mapping[int, float],
        steps: list[str],
    ) -> Shortlist | None:
        """Step 1 in parts (ADR-029): the catalog's parts read in parallel for recall (1a),
        their candidates pooled with the search engine's, then compared side by side (1b).
        If the comparison fails, the pool's first candidates go on (the parts' picks first)."""
        a = self.settings.analyst
        t0 = time.perf_counter()
        chunks = chunk_catalog(catalog, a.catalog_chunks)
        with trace.span("1a — katalog parçaları (paralel)", f"{len(chunks)} parça") as sp:
            read = read_chunks(query, chunks, self.llm, a.chunk_candidates, catalog.ids)
            if sp is not None and read is None:
                sp.status, sp.detail = "error", "hiçbir parça yanıt vermedi"
            elif sp is not None and read is not None:
                sp.status = "warn" if read.failed else "ok"
                sp.detail = (f"{len(read.candidates)} aday; "
                             f"{read.failed}/{read.parts} parça yanıtsız")
        if read is None:
            return None
        t1 = time.perf_counter()
        pool: dict[str, str] = dict(read.reasons)
        together = sorted(ranked, key=lambda m: (-len(m.covered), -m.score))
        for m in [*together[:POOL_RULE_TOGETHER], *ranked[:POOL_RULE_TOP]]:
            concepts = ", ".join(m.covered) or "-"
            pool.setdefault(m.object_key, f"arama motoru önerdi (kavramlar: {concepts})")
        keys = list(pool)[: a.pool_size]
        hits = term_matcher(read.search_terms)
        lines = []
        for key in keys:
            cols = self.objects[key].features
            best = sorted(cols, key=lambda f: -(relevance.get(f.col.id, 0.0) + 0.5 * hits(f.col)))
            names = ", ".join(f.col.column for f in best[: a.pool_columns])
            lines.append(
                f"{catalog.keys[key]} | {key} | {catalog.groups[key]} | {len(cols)} kolon | "
                f"ilgili kolonlar: {names} | neden aday: {pool[key] or '-'}"
            )
        with trace.span("1b — uzlaştırma", f"{len(keys)} adaylık havuz") as sp:
            short = reconcile(query, "\n".join(lines), self.llm, a.shortlist,
                              {catalog.keys[k]: k for k in keys}, catalog.ids)  # fmt: skip
            if sp is not None and short is None:
                sp.status, sp.detail = "warn", "yanıt yok — havuzun ilk adayları kullanıldı"
        t2 = time.perf_counter()
        failed = f", {read.failed} parça yanıt vermedi" if read.failed else ""
        steps.append(
            f"1a — katalog {read.parts} parçada paralel okundu: {len(read.candidates)} aday"
            f"{failed} ({t1 - t0:.0f} sn)"
        )
        if short is None:
            steps.append("1b — uzlaştırma yanıt vermedi; havuzun ilk adayları kullanıldı")
            return Shortlist(
                "", keys[: a.shortlist], {k: pool[k] for k in keys}, [], read.search_terms,
                read.unknown_ids,
            )  # fmt: skip
        steps.append(
            f"1b — {len(keys)} adaylık havuz yan yana kıyaslandı, {len(short.candidates)} "
            f"final aday seçildi ({t2 - t1:.0f} sn)"
        )
        short.unknown_ids += read.unknown_ids
        short.search_terms = short.search_terms or read.search_terms
        return short

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
                reply, reading.ids, columns_of, checker, top_n, a.min_confidence, catalog.ids
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
        notes += quality_notes(objects)
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
            *reading.steps,
            "Okunan adaylar: " + (", ".join(k.rsplit(".", 1)[-1] for k in short.candidates) or "-"),
            "Benzer (uyarı) tablolar: "
            + (", ".join(k.rsplit(".", 1)[-1] for k in short.confusables) or "-"),
            "Aile aramasıyla eklenen: "
            + (", ".join(f"{k.rsplit('.', 1)[-1]} ({f})" for k, f in added.items()) or "-"),
            f"2. adım — adayların {sum(len(columns_of[k]) for k in readable)} kolonu "
            f"sözlük açıklamalarıyla okundu, rapor yazıldı ({t3 - t2:.0f} sn)",
            "Arama motoru (BM25"
            + (" + anlamsal arama" if self.hybrid else "")
            + ") sonuçları modele ipucu ve benzer alan kanıtı olarak verildi",
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
            llm_unknown_ids=short.unknown_ids,
            interpretation=short.interpretation,
            design=answer.design,
            attention=answer.attention,
            analyst=True,
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
            for doc, _ in self.topic_index.search(query, top_k=a.family_tables * 4):
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

    def _concept_evidence(self, key: str, q: ExpandedQuery, relevance: Mapping[int, float]) -> str:
        """Which request concepts the table carries, and in which column (§8, lexical)."""
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
                search_score=0.0,
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

    def _analyze_rules(self, query: str, top_n: int = 5) -> AnalysisResult:
        started = time.perf_counter()
        s = self.settings
        ranked, q, judged = self.rank(query)
        ranked, dropped = validate(ranked, self.column_keys)

        top = ranked[:top_n]
        near = ranked[top_n : top_n + NEAR_MISS_COUNT]
        if (
            not top
            or top[0].score < s.scoring.min_answer_score
            or top[0].components.get("coverage", 1.0) < s.scoring.min_answer_coverage
        ):
            verdict = Verdict.NOT_FOUND
            near, top = top[:NEAR_MISS_COUNT], []
        elif top[0].level.value == "Yüksek" and not top[0].missing:
            verdict = Verdict.FOUND
        else:
            verdict = Verdict.PARTIAL
        for m in (*top, *near):
            explain(m, q)
            if m.llm_reason:
                apply_llm_texts(m)

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
        notes += clarification_notes(q, self.clarifications)
        notes += join_suggestions(top, q, self.join_keys)
        for m in near:
            notes.append(
                Note(
                    "Yakın aday",
                    m.object_key,
                    f"Güven %{round(m.score * 100)} — {m.reason}",
                )
            )
        notes += quality_notes(top)
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
            "Skorlama: kural tabanlı; obje seviyesinde en iyi kolon + kapsama + zaman "
            "+ granülerlik",
            "LLM: kullanılmadı"
            if judged is None
            else f"LLM hakem: {self.llm.model} (ilk {s.llm.judge_candidates} aday; "
            f"final = {s.scoring.w_rule:g} × kural + {s.scoring.w_llm:g} × LLM)",
        ]
        if self.hybrid:
            method.insert(1, f"Anlamsal arama: {self.dense.model if self.dense else ''} "
                          f"(ağırlık {s.dense.weight:g}, ilk {s.dense.top_k} kolon)")  # fmt: skip
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
            llm_model=self.llm.model if judged is not None else "",
            llm_unknown_ids=judged.unknown_ids if judged is not None else 0,
        )


def _object_dense_for(
    settings: Settings, objects: Mapping[str, ObjectColumns]
) -> ObjectDenseIndex | None:
    if not settings.dense.enabled:
        return None
    return load_object_index(Path(settings.index.dir), objects)


def _dense_for(settings: Settings, n_columns: int) -> DenseIndex | None:
    if not settings.dense.enabled:
        return None
    index = load_dense_index(Path(settings.index.dir), n_columns)
    if index is None:
        log.warning("Vektör indeksi bulunamadı; `vsa index --dense` ile kurun. Yalnız BM25.")
    return index


def fallback_reason(error: str) -> str:
    """Plain Turkish reason for an analyst failure, from the model server's error text."""
    text = fold(error)
    if "context" in text and ("exceed" in text or "size" in text or "length" in text):
        return (
            "Modelin bağlam penceresi tablo kataloğu için küçük. Yerel modeli daha geniş "
            "bağlamla yükleyin (LM Studio'da Context Length) veya ayarlardan bulut modelini seçin."
        )
    if "timed out" in text or "timeout" in text or "504" in text:
        return "Model zamanında yanıt vermedi (zaman aşımı)."
    if "connection" in text or "ulasilamadi" in text or "refused" in text:
        return "Model sunucusuna ulaşılamadı."
    return f"Model hatası: {error[:160]}" if error else "Model yanıt vermedi."


def ranked_keys(engine: Engine, queries: Sequence[str]) -> list[list[str]]:
    return [[m.object_key for m in engine.rank_objects(q)[0]] for q in queries]
