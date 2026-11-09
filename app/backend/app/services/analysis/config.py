"""Search and answer settings of the engine with their measured defaults.

The defaults are the measured settings (2026-10-07: 294 questions, ~%89,8). Which of them the
admin screen shows, their labels and ranges, and how changed values are kept belong to the
search-settings PRD; the engine only reads them. The model connection is not a setting here:
it comes from the llm-connection PRD through the model port.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BM25Settings:
    k1: float = 1.2
    b: float = 0.75


@dataclass(slots=True)
class SearchSettings:
    # Objects reached through their best columns in the top N of BM25 are scored as a whole.
    candidate_object_columns: int = 1000
    top_k_objects: int = 20
    field_weights: dict[str, float] = field(
        default_factory=lambda: {"name": 3.0, "synonyms": 2.0, "description": 1.0, "object": 1.0}
    )
    bm25: BM25Settings = field(default_factory=BM25Settings)


@dataclass(slots=True)
class ExpansionSettings:
    enabled: bool = True  # corporate term dictionary
    synonyms: bool = True  # the dictionary's Synonyms column (ADR-046)
    weight: float = 0.6


@dataclass(slots=True)
class ObjectWeights:
    # best column : coverage : time : granularity = 5:3:1:1, plus topic fit (ADR-028)
    best_column: float = 0.35
    coverage: float = 0.21
    time: float = 0.07
    granularity: float = 0.07
    topic: float = 0.30  # object-level topic fit (ADR-028)


@dataclass(slots=True)
class ScoringSettings:
    min_candidate_score: float = 0.5
    # The rule answer (Engine.rule_answer) is never shown (ADR-038); these three shape it
    # for measurement only (the M1 acceptance test holds them).
    min_answer_score: float = 0.35
    min_answer_coverage: float = 0.5  # ADR-013
    rule_only_factor: float = 0.8
    object: ObjectWeights = field(default_factory=ObjectWeights)


@dataclass(slots=True)
class AnalystSettings:
    """The analyst flow (ADR-029, ADR-040): the only way an answer is written (ADR-038).
    The rule engine stays as evidence and validator (ADR-002)."""

    shortlist: int = 14  # candidate tables the model reads column by column
    confusables: int = 6  # look-alike tables it reads for the warnings
    family_tables: int = 2  # tables added per information family by term search
    family_extra: int = 6  # at most this many tables added that way
    # Safety net: the table-level word search's best tables (object profiles included)
    # that step 1 did not pick are read in step 2 as well. 0 = off.
    search_tables: int = 3
    evidence_columns: int = 60  # look-alike columns from the whole dictionary
    description_chars: int = 420  # per column description in the material
    full_table_columns: int = 90  # wider tables: lines only for the relevant columns
    # ADR-040: columns go as "Ad [Rol]: özet"; only this many of the most relevant ones per
    # table carry the full description (-1 = every column, the pre-ADR-040 material).
    detail_columns: int = 8
    min_confidence: float = 0.5  # recommendations below this are not shown (ADR-006)
    max_tokens: int = 8000  # answer budget of the second step
    # Reply budget of the first step (catalog shortlist); was a fixed 2500, which a thinking
    # model could fill before writing its JSON (output_truncated).
    shortlist_max_tokens: int = 8000


@dataclass(slots=True)
class CacheSettings:
    """Earlier analyst answers given again (ADR-035)."""

    enabled: bool = True
    meaning: bool = True  # also for a question with the same concepts in other words
    max_age_days: int = 30  # older answers are written anew; 0 = no limit


@dataclass(slots=True)
class Settings:
    search: SearchSettings = field(default_factory=SearchSettings)
    expansion: ExpansionSettings = field(default_factory=ExpansionSettings)
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    analyst: AnalystSettings = field(default_factory=AnalystSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
