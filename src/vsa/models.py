"""Core data types shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FlagKind(StrEnum):
    """Quality flags attached to a dictionary column (HANDOVER §3.3, §3.4)."""

    MODEL_ESTIMATED = "model_estimated"  # [MODEL TAHMİNİ — DOĞRULANMALI] -> score ×0.85
    CORRECTED = "corrected"  # [ORİJİNAL AÇIKLAMA HATALIYDI — DÜZELTİLDİ ...] -> note only
    NEEDS_VERIFICATION = "needs_verification"  # other leading [...] notes -> note only
    NAMING_MISMATCH = "naming_mismatch"  # Sheet2 "İsimlendirme/İçerik Uyumsuzluğu" -> ×0.90
    QUALITY_NOTE = "quality_note"  # any other Sheet2 finding -> note only


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


@dataclass(slots=True)
class Dictionary:
    """A loaded data dictionary plus provenance."""

    columns: list[DictColumn]
    source_path: str
    version: str  # "<sha256[:12]>-<row count>" (HANDOVER §3.6)
    warnings: list[str] = field(default_factory=list)

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
    # LLM judge (M4): rule score before combination and the judge's verdict, if any.
    rule_score: float | None = None
    llm_confidence: float | None = None
    llm_reason: str = ""
    llm_caveat: str = ""
    llm_usage: str = ""
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
    llm_model: str = ""  # set when the LLM judge ran
    llm_unknown_ids: int = 0  # judge answers outside the candidate list (hallucination)
    # Analyst flow (ADR-029): how the request was read, how to combine the suggested
    # tables ("Önerilen Kurgu") and the traps to watch ("Dikkat Edilmesi Gerekenler").
    interpretation: str = ""
    design: list[str] = field(default_factory=list)
    attention: list[str] = field(default_factory=list)
    analyst: bool = False  # True when the analyst flow wrote this answer
    dictionary_objects: int = 0  # tables in the dictionary, for the report header


# --------------------------------------------------------------------------- batch (M5)


class FieldStatus(StrEnum):
    READY = "Hazır"
    PARTIAL = "Kısmen hazır"
    DERIVE = "Türetilmeli"
    NOT_FOUND = "Bulunamadı"


@dataclass(frozen=True, slots=True)
class RequestField:
    """One row of a target-table request: TR title / EN title / description."""

    index: int
    tr: str
    en: str
    description: str = ""

    @property
    def label(self) -> str:
        return self.en or self.tr


@dataclass(slots=True)
class FieldCandidate:
    match: ObjectMatch
    score: float  # field-level score incl. core-table context bonus
    in_core: bool = False
    derivation: str = ""  # e.g. "COUNT(DISTINCT ReceiverBankName)"
    notes: list[str] = field(default_factory=list)
    wide_family: bool = False  # core table answers by summing per-channel columns
    fits_measure: bool = True  # False: e.g. an amount column offered for a distinct count


@dataclass(slots=True)
class FieldResult:
    field: RequestField
    status: FieldStatus
    candidates: list[FieldCandidate]

    @property
    def best(self) -> FieldCandidate | None:
        return self.candidates[0] if self.candidates else None


@dataclass(slots=True)
class TableCoverage:
    """How many requested fields a single object can serve (§4.1)."""

    object_key: str
    object_name: str
    fields: list[str]  # labels of fields this object serves
    ready: int
    partial: int
    mean_score: float


@dataclass(slots=True)
class BatchResult:
    name: str
    verdict: Verdict
    summary: str
    fields: list[FieldResult]
    coverage: list[TableCoverage]
    notes: list[Note]
    time_grain: str  # "aylık" / "günlük" / ""
    dictionary_source: str
    dictionary_version: str
    generated_at: str
    method: list[str]
    elapsed_ms: int = 0
    # Analyst flow (ADR-029), as in AnalysisResult.
    interpretation: str = ""
    design: list[str] = field(default_factory=list)
    attention: list[str] = field(default_factory=list)
    analyst: bool = False
