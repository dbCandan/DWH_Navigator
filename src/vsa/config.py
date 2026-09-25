"""Settings: defaults + optional YAML override (HANDOVER §15)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml


@dataclass(slots=True)
class DictionarySettings:
    path: str = "data/DataDictionary-Final.xlsx"
    sheet: str = "Sheet1"
    quality_sheet: str | None = "Sheet2"


@dataclass(slots=True)
class IndexSettings:
    dir: str = "data/index"


@dataclass(slots=True)
class BM25Settings:
    k1: float = 1.2
    b: float = 0.75


@dataclass(slots=True)
class SearchSettings:
    top_k_columns: int = 120
    # Objects reached through their best columns in the top N of BM25 are scored as a
    # whole; wider than top_k_columns so coverage-driven winners are not missed (§8).
    candidate_object_columns: int = 400
    top_k_objects: int = 10
    field_weights: dict[str, float] = field(
        default_factory=lambda: {"name": 3.0, "synonyms": 2.0, "description": 1.0, "object": 1.0}
    )
    bm25: BM25Settings = field(default_factory=BM25Settings)


@dataclass(slots=True)
class ExpansionSettings:
    enabled: bool = True  # corporate term dictionary (§7.2a)
    synonyms: bool = True  # dictionary's own synonym sections (§7.2b)
    weight: float = 0.6
    term_dictionary: str = "config/term_dictionary.csv"
    stopwords: str = "config/stopwords_tr.txt"


@dataclass(slots=True)
class ObjectWeights:
    best_column: float = 0.50
    coverage: float = 0.30
    time: float = 0.10
    granularity: float = 0.10


@dataclass(slots=True)
class FlagPenalty:
    model_estimated: float = 0.85
    naming_mismatch: float = 0.90


@dataclass(slots=True)
class ScoringSettings:
    w_rule: float = 0.6
    w_llm: float = 0.4
    min_candidate_score: float = 0.25
    min_answer_score: float = 0.35
    min_answer_coverage: float = 0.5  # ADR-013
    object: ObjectWeights = field(default_factory=ObjectWeights)
    flag_penalty: FlagPenalty = field(default_factory=FlagPenalty)


@dataclass(slots=True)
class LLMSettings:
    enabled: bool = False
    endpoint: str = ""  # OpenAI-compatible base URL, e.g. http://localhost:1234/v1
    model: str = ""  # chat model for judge / query expansion
    embedding_model: str = ""  # for the dense index (M3)
    temperature: float = 0.1
    timeout: int = 120
    api_key: str = ""
    judge: bool = True  # LLM judge on top candidates (§10)
    judge_candidates: int = 8  # objects shown to the judge
    expand_query: bool = False  # LLM query expansion into the BM25 arm (§7.2c)


@dataclass(slots=True)
class DenseSettings:
    enabled: bool = False
    top_k: int = 200  # dense column candidates
    rrf_k: int = 60  # reciprocal rank fusion constant
    weight: float = 0.35  # share of the dense similarity in the column search score


@dataclass(slots=True)
class ReportSettings:
    out_dir: str = "out"


@dataclass(slots=True)
class Settings:
    dictionary: DictionarySettings = field(default_factory=DictionarySettings)
    index: IndexSettings = field(default_factory=IndexSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    expansion: ExpansionSettings = field(default_factory=ExpansionSettings)
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    dense: DenseSettings = field(default_factory=DenseSettings)
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


DEFAULT_SETTINGS_PATH = Path("config/settings.yaml")


def load_settings(path: Path | None = None) -> Settings:
    """Load settings; missing file -> defaults. Unknown keys are an error (typo guard)."""
    settings = Settings()
    target = path or DEFAULT_SETTINGS_PATH
    if target.exists():
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        _merge(settings, raw)
    return settings
