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
