"""Settings: defaults + optional YAML override (HANDOVER §15)."""

from __future__ import annotations

import os
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
    # 0.35 : 0.21 : 0.07 : 0.07 keeps the §8 ratio 5:3:1:1 when topic fit is off (ADR-028)
    best_column: float = 0.35
    coverage: float = 0.21
    time: float = 0.07
    granularity: float = 0.07
    topic: float = 0.30  # object-level topic fit (ADR-028)


@dataclass(slots=True)
class FlagPenalty:
    model_estimated: float = 0.85
    naming_mismatch: float = 0.90


@dataclass(slots=True)
class ScoringSettings:
    w_rule: float = 0.75  # ADR-022 (HANDOVER default 0.6)
    w_llm: float = 0.25
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
    reasoning_effort: str = "none"  # reasoning models answer directly ("" = don't send)
    # Where the judge runs: "local" (endpoint above) or "cloud" (the ``cloud`` section).
    # Embeddings always stay on the local endpoint. "cloud" sends every request's
    # candidate tables out of the network — the user's decision (ADR-026, 2026-09-26).
    provider: str = "local"
    seed: int = 42  # fixed sampling seed for repeatable judgments; -1 = don't send
    judge: bool = True  # LLM judge on top candidates (§10)
    judge_candidates: int = 8  # objects shown to the judge
    expand_query: bool = False  # LLM query expansion into the BM25 arm (§7.2c)


@dataclass(slots=True)
class AnalystSettings:
    """LLM analyst flow for ``ask`` (ADR-029). Runs whenever the chat model is on; the
    rule pipeline stays as evidence, validator and fallback (ADR-002, ADR-008)."""

    enabled: bool = True
    shortlist: int = 14  # candidate tables the model reads column by column
    confusables: int = 6  # look-alike tables it reads for the warnings
    family_tables: int = 2  # tables added per information family by term search
    family_extra: int = 6  # at most this many tables added that way
    # Target-table requests through the analyst too. Off: on golden b001 it scored below
    # the rule passes (recall@5 0.70 vs 0.90, columns 0.57 vs 0.86; ADR-029).
    batch: bool = False
    evidence_columns: int = 60  # look-alike columns from the whole dictionary
    description_chars: int = 420  # per column description in the material
    full_table_columns: int = 90  # wider tables: descriptions only for relevant columns
    min_confidence: float = 0.5  # recommendations below this are not shown (ADR-006)
    max_tokens: int = 8000  # answer budget of the second step


@dataclass(slots=True)
class DenseSettings:
    enabled: bool = False
    top_k: int = 200  # dense column candidates
    rrf_k: int = 60  # reciprocal rank fusion constant
    weight: float = 0.35  # share of the dense similarity in the column search score


@dataclass(slots=True)
class CloudSettings:
    """Hosted models, for the model lab only (NVIDIA API catalog, ADR-026).

    The app's judge never uses this: the lab sends test questions and dictionary
    metadata (table/column names and descriptions) out of the network, the app would
    send real requests. Off unless the user switches it on.
    """

    enabled: bool = False
    endpoint: str = "https://integrate.api.nvidia.com/v1"  # any OpenAI-compatible API
    api_key: str = ""  # else the NVIDIA_API_KEY environment variable
    rpm: int = 30  # requests per minute (NVIDIA's free tier allows ~40)


CLOUD_PREFIX = "cloud:"  # lab model ids: "cloud:meta/llama-3.3-70b-instruct"


GOOGLE_AI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai"


def cloud_api_key(cloud: CloudSettings) -> str:
    """Key for the hosted endpoint. Google AI Studio reads GEMINI_API_KEY first, so the
    saved NVIDIA key can stay in the file for switching back; NVIDIA falls back to
    NVIDIA_API_KEY when no key is saved."""
    if "generativelanguage.googleapis.com" in cloud.endpoint:
        return user_env("GEMINI_API_KEY") or user_env("GOOGLE_API_KEY")
    return cloud.api_key or user_env("NVIDIA_API_KEY")


def user_env(name: str) -> str:
    """An environment variable, or on Windows the user's saved one (``setx`` only reaches
    programs started afterwards, not a console that was already open)."""
    value = os.environ.get(name, "")
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return ""


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
    analyst: AnalystSettings = field(default_factory=AnalystSettings)
    dense: DenseSettings = field(default_factory=DenseSettings)
    cloud: CloudSettings = field(default_factory=CloudSettings)
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
