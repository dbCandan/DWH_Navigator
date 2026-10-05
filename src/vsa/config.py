"""Settings: defaults + optional YAML override (HANDOVER §15)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml

from vsa.llm.integrations import Integration, from_dict
from vsa.llm.integrations import apply as apply_integrations


@dataclass(slots=True)
class DictionarySettings:
    path: str = "data/VeriSozlugu.xlsx"
    sheet: str = "Kolonlar"
    quality_sheet: str | None = None


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
    min_candidate_score: float = 0.25
    min_answer_score: float = 0.35
    min_answer_coverage: float = 0.5  # ADR-013
    # Rule-engine answers (no model, or the model failed): confidence shown = rule score ×
    # this. On the golden set the rules put the right table first 3 times in 8, the analyst
    # 7 in 8 (ADR-029); a rule answer must not look as sure as an analyst's (ADR-034).
    rule_only_factor: float = 0.8
    object: ObjectWeights = field(default_factory=ObjectWeights)
    flag_penalty: FlagPenalty = field(default_factory=FlagPenalty)


@dataclass(slots=True)
class LLMSettings:
    """Model connection. With ``config/llm_integrations.yaml`` (the admin screen's LLM page,
    ADR-032) the connection fields come from the active integrations; without it, from here."""

    enabled: bool = False
    endpoint: str = ""  # OpenAI-compatible base URL, e.g. http://127.0.0.1:1234/v1
    model: str = ""  # chat model: the analyst (ADR-029)
    embedding_model: str = ""  # for the dense index (M3)
    embedding_endpoint: str = ""  # embeddings on a server of their own; "" = endpoint
    embedding_api_key: str = ""  # key of that server; "" = api_key
    temperature: float = 0.1
    timeout: int = 120
    api_key: str = ""
    reasoning_effort: str = "none"  # reasoning models answer directly ("" = don't send)
    seed: int = 42  # fixed sampling seed for repeatable judgments; -1 = don't send


@dataclass(slots=True)
class AnalystSettings:
    """The analyst flow (ADR-029). Runs whenever a chat model is connected; the rule
    engine stays as evidence, validator and fallback (ADR-002, ADR-008)."""

    shortlist: int = 14  # candidate tables the model reads column by column
    confusables: int = 6  # look-alike tables it reads for the warnings
    family_tables: int = 2  # tables added per information family by term search
    family_extra: int = 6  # at most this many tables added that way
    evidence_columns: int = 60  # look-alike columns from the whole dictionary
    description_chars: int = 420  # per column description in the material
    full_table_columns: int = 90  # wider tables: descriptions only for relevant columns
    min_confidence: float = 0.5  # recommendations below this are not shown (ADR-006)
    max_tokens: int = 8000  # answer budget of the second step
    # Step 1 split (ADR-029): the catalog read in N parallel parts for recall, then the
    # pooled candidates compared side by side. 1 = the whole catalog in one call.
    catalog_chunks: int = 5
    chunk_candidates: int = 8  # candidates each part may propose
    pool_size: int = 40  # pooled candidates the reconcile step compares
    pool_columns: int = 12  # most relevant column names shown per pooled table


@dataclass(slots=True)
class DenseSettings:
    enabled: bool = False
    top_k: int = 200  # dense column candidates
    weight: float = 0.35  # share of the dense similarity in the column search score


@dataclass(slots=True)
class CacheSettings:
    """Earlier analyst answers given again (ADR-035)."""

    enabled: bool = True
    meaning: bool = True  # also for a question with the same concepts in other words
    max_age_days: int = 30  # older answers are written anew; 0 = no limit


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
    cache: CacheSettings = field(default_factory=CacheSettings)
    report: ReportSettings = field(default_factory=ReportSettings)


T = TypeVar("T")


# Settings of removed features (judge, LLM query expansion, target-table mode; ADR-033):
# older files still carry them, they are ignored instead of failing the typo guard.
RETIRED = frozenset({
    "llm.judge", "llm.judge_candidates", "llm.expand_query", "llm.provider",
    "scoring.w_rule", "scoring.w_llm", "analyst.enabled", "analyst.batch", "dense.rrf_k",
})  # fmt: skip


def _merge(obj: T, data: dict[str, Any], path: str = "") -> T:
    """Recursively overlay a YAML mapping onto a dataclass instance."""
    known = {f.name for f in fields(obj)}  # type: ignore[arg-type]
    for key, value in data.items():
        if f"{path}{key}" in RETIRED:
            continue
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
INTEGRATIONS_FILE = "llm_integrations.yaml"  # next to settings.yaml; holds API keys


def integrations_path(settings_path: Path | None = None) -> Path:
    return (settings_path or DEFAULT_SETTINGS_PATH).parent / INTEGRATIONS_FILE


def read_integrations(path: Path) -> list[Integration] | None:
    """The saved integrations; None when there is no file (``llm:`` settings rule)."""
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [from_dict(d) for d in raw.get("integrations") or [] if isinstance(d, dict)]


def write_integrations(path: Path, items: list[Integration]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# LLM entegrasyonları — Yönetim → Ayarlar → Yapay zekâ ekranından yazılır (ADR-032).\n"
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
    target = path or DEFAULT_SETTINGS_PATH
    if target.exists():
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        _merge(settings, raw)
    items = read_integrations(integrations_path(target))
    if items is not None:
        apply_integrations(settings.llm, items)
    return settings
