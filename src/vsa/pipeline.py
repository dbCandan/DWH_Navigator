"""Orchestration (HANDOVER §4): query -> search -> column rules -> object
aggregation -> validation -> explained result. Pure given its inputs; the
``Engine.from_*`` constructors are the only parts that touch files.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from vsa.config import Settings
from vsa.expansion.query_expander import (
    Concept,
    ExpandedQuery,
    QueryExpander,
    build_synonym_index,
)
from vsa.features import ColumnFeatures, build_features
from vsa.index.bm25 import BM25Index, weighted_fields
from vsa.index.dense import DenseIndex, load_dense_index, normalize
from vsa.index.store import load_index, save_index
from vsa.llm.client import LLMClient, LLMError, NullClient, client_from_settings
from vsa.llm.judge import JudgeResult, judge
from vsa.llm.prompts import EXPAND_SCHEMA, EXPAND_SYSTEM, expand_user
from vsa.loader import load_dictionary, load_stopword_file, load_term_dictionary
from vsa.models import AnalysisResult, ColumnHit, Dictionary, Note, ObjectMatch, TermGroup, Verdict
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
from vsa.text.normalize import tokenize
from vsa.validate import validate

log = logging.getLogger(__name__)

CLARIFICATIONS_PATH = Path("config/clarifications.yaml")
NEAR_MISS_COUNT = 3


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
        return cls(
            dictionary,
            settings,
            Resources.from_settings(settings),
            llm=client_from_settings(settings.llm),
            dense=_dense_for(settings, len(dictionary.columns)),
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
            dense=_dense_for(settings, len(dictionary.columns)),
        )
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
        self, query: str, include: Iterable[str] = ()
    ) -> tuple[list[ObjectMatch], ExpandedQuery]:
        """Ranked objects for a query (no answer threshold). Objects in ``include`` are
        always scored and kept, even when search alone would not reach them — batch
        mode uses this to judge every field against the core table."""
        s = self.settings
        q = self.expander.expand(query)
        self._weigh_concepts(q)
        self._llm_expand(q)
        scored = self.bm25.search(q.sparse_terms, top_k=len(self.features))
        bm25_map = dict(scored)
        max_bm25 = scored[0][1] if scored else 0.0

        pool = {doc for doc, _ in scored[: s.search.candidate_object_columns]}
        pool |= set(q.synonym_hits)

        # M3: the dense arm uses the original wording (ADR-004) and widens the pool with
        # semantically close columns that share no words with the request.
        qvec = self._query_vector(q.dense_text) if s.dense.enabled else None
        dense_lo = dense_hi = 0.0
        if qvec is not None and self.dense is not None:
            dense_top = self.dense.search(qvec, s.dense.top_k)
            pool |= {i for i, _ in dense_top}
            dense_hi, dense_lo = dense_top[0][1], dense_top[-1][1]

        forced = {k for k in include if k in self.objects}
        candidate_objects = {self.features[i].col.object_key for i in pool} | forced

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
        ranked = aggregate(
            hits,
            q,
            {k: self.objects[k] for k in candidate_objects},
            s.scoring.object,
            s.scoring.min_candidate_score,
        )
        limit = s.search.top_k_objects + NEAR_MISS_COUNT
        kept = [
            m
            for i, m in enumerate(ranked)
            if m.object_key in forced or (i < limit and m.score >= s.scoring.min_candidate_score)
        ]
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

    def analyze(self, query: str, top_n: int = 5) -> AnalysisResult:
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
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            method=method,
            dropped_by_validation=dropped,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            llm_model=self.llm.model if judged is not None else "",
            llm_unknown_ids=judged.unknown_ids if judged is not None else 0,
        )


def _dense_for(settings: Settings, n_columns: int) -> DenseIndex | None:
    if not settings.dense.enabled:
        return None
    index = load_dense_index(Path(settings.index.dir), n_columns)
    if index is None:
        log.warning("Vektör indeksi bulunamadı; `vsa index --dense` ile kurun. Yalnız BM25.")
    return index


def ranked_keys(engine: Engine, queries: Sequence[str]) -> list[list[str]]:
    return [[m.object_key for m in engine.rank_objects(q)[0]] for q in queries]
