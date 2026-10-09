"""Settings: defaults + optional YAML override (data/settings.yaml).

The defaults are the measured settings (2026-10-07: 294 questions, ~%89,8); a new install
needs no settings file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml

from vsa.llm.integrations import Integration, from_dict
from vsa.llm.integrations import apply as apply_integrations


@dataclass(slots=True)
class DictionarySettings:
    # ADR-050: the app's one dictionary. Workbooks in the dictionary template only come in
    # (import) and go out (export); the app never reads a workbook as its dictionary.
    store: str = "data/dictionary.jsonl"


@dataclass(slots=True)
class IndexSettings:
    dir: str = "data/index"


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
    term_dictionary: str = "data/terms.jsonl"
    stopwords: str = "data/stopwords.jsonl"


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
class LLMSettings:
    """Model connection. With ``data/llm_integrations.yaml`` (the admin screen's LLM page,
    ADR-032) the connection fields come from the active integrations; without it, from here."""

    enabled: bool = False
    endpoint: str = ""  # OpenAI-compatible base URL, e.g. http://127.0.0.1:1234/v1
    model: str = ""  # chat model: the analyst (ADR-029)
    temperature: float = 0.0
    timeout: int = 900  # an analysis takes minutes on the model server
    api_key: str = ""
    reasoning_effort: str = "none"  # reasoning models answer directly ("" = don't send)
    seed: int = 42  # fixed sampling seed for repeatable judgments; -1 = don't send


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


@dataclass(slots=True)
class CacheSettings:
    """Earlier analyst answers given again (ADR-035)."""

    enabled: bool = True
    meaning: bool = True  # also for a question with the same concepts in other words
    max_age_days: int = 30  # older answers are written anew; 0 = no limit


@dataclass(slots=True)
class ReportSettings:
    out_dir: str = "data/out"


@dataclass(slots=True)
class Settings:
    dictionary: DictionarySettings = field(default_factory=DictionarySettings)
    index: IndexSettings = field(default_factory=IndexSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    expansion: ExpansionSettings = field(default_factory=ExpansionSettings)
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    analyst: AnalystSettings = field(default_factory=AnalystSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    report: ReportSettings = field(default_factory=ReportSettings)


T = TypeVar("T")


def _merge(obj: T, data: dict[str, Any], path: str = "") -> T:
    """Recursively overlay a YAML mapping onto a dataclass instance."""
    known = {f.name for f in fields(obj)}  # type: ignore[arg-type]
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Bilinmeyen ayar: {path}{key}")
        current = getattr(obj, key)
        if is_dataclass(current) and isinstance(value, dict):
            _merge(current, value, f"{path}{key}.")
        elif isinstance(current, dict) and isinstance(value, dict):
            current.update(value)
        else:
            setattr(obj, key, value)
    return obj


# Everything the app reads and writes lives in data/ (ADR-052), as in the container.
DEFAULT_SETTINGS_PATH = Path("data/settings.yaml")
INTEGRATIONS_FILE = "llm_integrations.yaml"  # next to settings.yaml; holds API keys


def settings_path(path: Path | None = None) -> Path:
    """The settings file to use: the given one, else data/settings.yaml."""
    return DEFAULT_SETTINGS_PATH if path is None else path


def integrations_path(path: Path | None = None) -> Path:
    return settings_path(path).parent / INTEGRATIONS_FILE


def read_integrations(path: Path) -> list[Integration] | None:
    """The saved integrations; None when there is no file (``llm:`` settings rule)."""
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [from_dict(d) for d in raw.get("integrations") or [] if isinstance(d, dict)]


def write_integrations(path: Path, items: list[Integration]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# LLM entegrasyonları — Yönetim → Yapay zekâ sayfasından yazılır (ADR-032).\n"
        "# API anahtarları içerir: repoya girmez, paylaşmayın.\n"
    )
    body = yaml.safe_dump(
        {"integrations": [i.to_dict() for i in items]}, allow_unicode=True, sort_keys=False
    )
    path.write_text(header + body, encoding="utf-8")


def load_settings(path: Path | None = None) -> Settings:
    """Load settings; missing file -> defaults. Unknown keys are an error (typo guard).
    Active LLM integrations, when their file exists, set the model connection (ADR-032)."""
    settings = Settings()
    target = settings_path(path)
    if target.exists():
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        _merge(settings, raw)
    items = read_integrations(integrations_path(target))
    if items is not None:
        apply_integrations(settings.llm, items)
    return settings
