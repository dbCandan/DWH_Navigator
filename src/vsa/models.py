"""Core data types shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FlagKind(StrEnum):
    """Quality flags attached to a dictionary column (HANDOVER §3.3, §3.4)."""

    MODEL_ESTIMATED = "model_estimated"  # [MODEL TAHMİNİ — DOĞRULANMALI] -> note only
    CORRECTED = "corrected"  # [ORİJİNAL AÇIKLAMA HATALIYDI — DÜZELTİLDİ ...] -> note only
    NEEDS_VERIFICATION = "needs_verification"  # other leading [...] notes -> note only


@dataclass(frozen=True, slots=True)
class Flag:
    kind: FlagKind
    text: str


@dataclass(frozen=True, slots=True)
class DictColumn:
    """One row of the data dictionary: a single column of a table/view."""

    id: int
    database: str
    schema: str
    object_name: str
    column: str
    description: str  # body text: leading flag and synonym section removed
    raw_description: str
    synonyms: tuple[str, ...] = ()
    flags: tuple[Flag, ...] = ()
    dataset_group: str | None = None
    has_pii: bool = False  # description mentions KVKK / kişisel veri (§18.5)
    role: str = ""  # Anahtar | Kod | Ad | Zaman | Ölçü | Bayrak | Metin
    summary: str = ""  # ≤70-char compressed meaning, what the LLM reads instead of description

    @property
    def object_key(self) -> str:
        return f"{self.database}.{self.schema}.{self.object_name}"

    @property
    def key(self) -> str:
        return f"{self.object_key}.{self.column}"

    def has_flag(self, kind: FlagKind) -> bool:
        return any(f.kind is kind for f in self.flags)


@dataclass(frozen=True, slots=True)
class TermGroup:
    """One row of the corporate term dictionary; matching is bidirectional."""

    term: str
    equivalents: tuple[str, ...]
    domain: str = ""
    note: str = ""

    @property
    def all_terms(self) -> tuple[str, ...]:
        return (self.term, *self.equivalents)


@dataclass(frozen=True, slots=True)
class ObjectProfile:
    """One row of the dictionary's object sheet: what a table holds, for the LLM catalog."""

    key: str  # DB.Schema.Object
    description: str = ""
    grain: str = ""  # what one row is
    key_columns: tuple[str, ...] = ()
    time_columns: tuple[str, ...] = ()
    domain: str = ""
    group: str = ""


@dataclass(slots=True)
class Dictionary:
    """A loaded data dictionary plus provenance."""

    columns: list[DictColumn]
    source_path: str
    version: str  # "<sha256[:12]>-<row count>" (HANDOVER §3.6)
    warnings: list[str] = field(default_factory=list)
    objects: dict[str, ObjectProfile] = field(default_factory=dict)

    def by_key(self) -> dict[str, DictColumn]:
        return {c.key: c for c in self.columns}

    @property
    def object_keys(self) -> set[str]:
        return {c.object_key for c in self.columns}


# --------------------------------------------------------------------------- results


class Level(StrEnum):
    HIGH = "Yüksek"
    MEDIUM = "Orta"
    LOW = "Düşük"


class Verdict(StrEnum):
    FOUND = "VAR"
    PARTIAL = "KISMEN VAR"
    NOT_FOUND = "BULUNAMADI"


@dataclass(slots=True)
class ColumnHit:
    """A candidate column with its rule score and the signals that produced it."""

    col: DictColumn
    search_score: float  # raw BM25
    rule_score: float
    raw_score: float = 0.0  # before clipping to [0, 1]; breaks ties between perfect matches
    signals: list[str] = field(default_factory=list)  # Turkish, human-readable
    caveats: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)  # labels of concepts it covers
    needs_derivation: bool = False
    role: str = ""  # why it is listed under the object: "eşleşme" / "kavram" / "zaman"


@dataclass(slots=True)
class ObjectMatch:
    object_key: str
    database: str
    schema: str
    object_name: str
    dataset_groups: list[str]
    score: float
    level: Level
    columns: list[ColumnHit]
    components: dict[str, float]
    covered: list[str]
    missing: list[str]
    reason: str = ""
    caveat: str = "-"
    usage: str = ""
    long_format_values: list[str] = field(default_factory=list)  # met via dimension column
    dimension_column: str = ""
    # Analyst flow (ADR-029): the rule engine's score next to the analyst's confidence.
    rule_score: float | None = None
    llm_confidence: float | None = None
    covers: str = ""  # analyst flow (ADR-029): "Kapsadığı Bilgi" in a few words


@dataclass(slots=True)
class Note:
    scope: str  # Kapsam / Netleştirme / Yakın aday / Veri kalitesi / Doğrulama
    title: str
    text: str


@dataclass(slots=True)
class AnalysisResult:
    query: str
    verdict: Verdict
    summary: str
    objects: list[ObjectMatch]
    near_misses: list[ObjectMatch]
    notes: list[Note]
    concepts: list[str]
    expansion_terms: list[str]
    dictionary_source: str
    dictionary_version: str
    generated_at: str
    method: list[str]
    dropped_by_validation: int = 0
    elapsed_ms: int = 0
    llm_model: str = ""  # the analyst's chat model; "" for a rule answer
    llm_unknown_ids: int = 0  # candidate ids the model made up (hallucination indicator)
    # Analyst flow (ADR-029): how the request was read, how to combine the suggested
    # tables ("Önerilen Kurgu") and the traps to watch ("Dikkat Edilmesi Gerekenler").
    interpretation: str = ""
    design: list[str] = field(default_factory=list)
    attention: list[str] = field(default_factory=list)
    analyst: bool = False  # True when the analyst flow wrote this answer
    fallback: str = ""  # why the analyst flow could not answer (rule answer shown instead)
    confidence_factor: float = 1.0  # rule answers: scores shown = rule score × this (ADR-034)
    dictionary_objects: int = 0  # tables in the dictionary, for the report header
    # ADR-035: an earlier answer given again — when it was written, to which question,
    # and how the questions matched ("aynı soru" / "aynı anlam"). Empty for a fresh answer.
    reused_at: str = ""
    reused_query: str = ""
    reused_match: str = ""


# --------------------------------------------------------------------------- list search


@dataclass(slots=True)
class ListItem:
    """One term of a list search (ADR-033): its answer, or why it has none."""

    index: int  # 1-based, as in the file
    term: str
    result: AnalysisResult | None = None
    error: str = ""
    elapsed_ms: int = 0


@dataclass(slots=True)
class ListResult:
    """A term list answered term by term through the one question flow."""

    name: str  # the uploaded file's name, for the report
    items: list[ListItem]
    dictionary_source: str
    dictionary_version: str
    generated_at: str
    cancelled: bool = False
    header: str = ""  # the list's first row, never searched
    notes: list[str] = field(default_factory=list)  # what the file check left out, and why
