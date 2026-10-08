"""The search and answer settings the admin screen may change (search-settings Requirement 1).

The schema is the source's ``web/settings_schema.py`` field for field: sections, keys, labels,
help texts, types, ranges, steps, display format, expert mark and effect (Decision 1). The five
file and folder fields are gone and the two texts that named a file or a removed command changed
(the ¹ texts of Requirement 1). Defaults are the engine's measured ``Settings()``; only values
that differ from them are stored (Decision 2), and the effective value is the default with the
stored value on top (Requirement 4).
"""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from enum import StrEnum
from typing import Any

from app.services.analysis.config import Settings


class SettingEffect(StrEnum):
    """``immediate``: the new engine keeps the word index; ``reindex``: the index is rebuilt."""

    IMMEDIATE = "immediate"
    REINDEX = "reindex"


class SettingRejection(StrEnum):
    """Why one submitted or stored value is refused (``search_settings.startup_invalid``)."""

    UNKNOWN = "unknown"
    TYPE = "type"
    RANGE = "range"


@dataclass(frozen=True, slots=True)
class SettingField:
    key: str
    label: str
    help: str
    type: str  # bool | int | float
    effect: SettingEffect = SettingEffect.IMMEDIATE
    format: str | None = None  # "pct": a 0-1 value shown as a percentage
    min: int | float | None = None
    max: int | float | None = None
    step: int | float | None = None
    advanced: bool = False


@dataclass(frozen=True, slots=True)
class SettingSection:
    id: str
    page: str  # search | data
    title: str
    intro: str
    fields: tuple[SettingField, ...]
    advanced: bool = False


_NOW = SettingEffect.IMMEDIATE
_REINDEX = SettingEffect.REINDEX


def _number(
    key: str,
    label: str,
    help: str,
    *,
    type: str,
    min: float,
    max: float,
    step: float,
    effect: SettingEffect = _NOW,
    format: str | None = None,
    advanced: bool = False,
) -> SettingField:
    return SettingField(key, label, help, type, effect, format, min, max, step, advanced)


SECTIONS: tuple[SettingSection, ...] = (
    SettingSection(
        id="analyst",
        page="search",
        title="Analist",
        intro="Cevabı sohbet modeli yazar: katalogdan aday seçer, sonra adayların kolonlarını "
        "okur; malzeme büyüdükçe yavaşlar.",
        fields=(
            _number(
                "analyst.shortlist",
                "Kolonları okunacak aday tablo sayısı",
                "1. adımda modelin seçebileceği en fazla tablo.",
                type="int",
                min=3,
                max=30,
                step=1,
            ),
            _number(
                "analyst.detail_columns",
                "Tam açıklamasıyla okunan kolon sayısı (tablo başına)",
                "En ilgili bu kadar kolon tam açıklamayla, kalanı “Ad [Rol]: özet” olarak gider.",
                type="int",
                min=0,
                max=60,
                step=1,
            ),
            _number(
                "analyst.min_confidence",
                "Gösterilecek en düşük model güveni",
                "Modelin bundan az emin olduğu tablolar önerilmez (“bulunamadı” geçerli cevap).",
                type="float",
                format="pct",
                min=0,
                max=1,
                step=0.05,
            ),
            _number(
                "analyst.max_tokens",
                "Cevap için en fazla token",
                "2. adımda modelin yazabileceği en uzun cevap.",
                type="int",
                min=1000,
                max=32000,
                step=500,
                advanced=True,
            ),
        ),
    ),
    SettingSection(
        id="terms",
        page="search",
        title="Eş anlamlılar ve terimler",
        intro="İş biriminin kelimelerini sözlüğe bağlar: “kredi” arayan “fon kullandırım”ı da "
        "bulur.",
        fields=(
            SettingField(
                "expansion.enabled",
                "Kurumsal terim sözlüğünü kullan",
                "Katılım bankacılığı terimleri ve kısaltmalar (Yönetim → Kelimeler).",
                "bool",
            ),
            SettingField(
                "expansion.synonyms",
                "Sözlüğün eş anlamlılarını kullan",
                "Sözlüğün Synonyms kolonundaki eş anlamlılar.",
                "bool",
            ),
            _number(
                "expansion.weight",
                "Eş anlamlı terimlerin ağırlığı",
                "Kullanıcının kendi yazdığı kelimeler %100 sayılır.",
                type="float",
                format="pct",
                min=0,
                max=1,
                step=0.05,
                advanced=True,
            ),
        ),
    ),
    SettingSection(
        id="ranking",
        page="search",
        advanced=True,
        title="Kural ipuçları (tablo sıralaması)",
        intro="Kural puanı (beş parça) modele ipucu olur, cevap yazmaz; değiştirmeden önce ve "
        "sonra altın setle ölçün.",
        fields=(
            _number(
                "scoring.object.best_column",
                "En iyi eşleşen kolon",
                "Tablodaki en iyi kolonun talebe uyumu.",
                type="float",
                min=0,
                max=1,
                step=0.05,
            ),
            _number(
                "scoring.object.coverage",
                "Kavramları birlikte taşıma",
                "Talepteki kavramların kaçı aynı tabloda.",
                type="float",
                min=0,
                max=1,
                step=0.05,
            ),
            _number(
                "scoring.object.topic",
                "Konu uyumu",
                "Tablonun bütün olarak talebin konusu olması; çok geniş tabloları dengeler.",
                type="float",
                min=0,
                max=1,
                step=0.05,
            ),
            _number(
                "scoring.object.time",
                "Zaman kolonu",
                "“Aylık”, “günlük” istenirse dönem/tarih kolonu var mı. İstenmezse sayılmaz.",
                type="float",
                min=0,
                max=1,
                step=0.05,
            ),
            _number(
                "scoring.object.granularity",
                "Müşteri seviyesi",
                "Müşteri bazlı talepte müşteri anahtarı var mı.",
                type="float",
                min=0,
                max=1,
                step=0.05,
            ),
            _number(
                "search.top_k_objects",
                "Değerlendirilen tablo sayısı",
                "Soru başına kural motorunun sıraladığı tablo sayısı (ipucu havuzu).",
                type="int",
                min=3,
                max=50,
                step=1,
            ),
            _number(
                "scoring.min_candidate_score",
                "İpucu listesine girecek en düşük kural puanı",
                "Bunun altındaki tablolar modele ipucu olarak gösterilmez.",
                type="float",
                format="pct",
                min=0,
                max=1,
                step=0.05,
            ),
        ),
    ),
    SettingSection(
        id="words",
        page="search",
        advanced=True,
        title="Kelime araması",
        intro="Kolon adı, eş anlamlı ve açıklamalarda BM25 araması; değerler indekse gömülü, "
        "değişince indeks yeniden kurulur.",
        fields=(
            _number(
                "search.field_weights.name",
                "Kolon adı ağırlığı",
                "",
                type="float",
                min=0,
                max=10,
                step=0.5,
                effect=_REINDEX,
            ),
            _number(
                "search.field_weights.synonyms",
                "Eş anlamlılar ağırlığı",
                "",
                type="float",
                min=0,
                max=10,
                step=0.5,
                effect=_REINDEX,
            ),
            _number(
                "search.field_weights.description",
                "Açıklama ağırlığı",
                "",
                type="float",
                min=0,
                max=10,
                step=0.5,
                effect=_REINDEX,
            ),
            _number(
                "search.field_weights.object",
                "Tablo adı ağırlığı",
                "",
                type="float",
                min=0,
                max=10,
                step=0.5,
                effect=_REINDEX,
            ),
            _number(
                "search.candidate_object_columns",
                "Aday tablo için taranan kolon",
                "Kavramları birlikte taşıyan tablolar kaçmasın diye geniş tutulur.",
                type="int",
                min=50,
                max=3000,
                step=50,
            ),
            _number(
                "search.bm25.k1",
                "BM25 k1",
                "Aynı kelimenin tekrarı ne kadar sayılsın.",
                type="float",
                min=0.1,
                max=3,
                step=0.1,
                effect=_REINDEX,
            ),
            _number(
                "search.bm25.b",
                "BM25 b",
                "Uzun açıklamalar ne kadar dengelensin.",
                type="float",
                min=0,
                max=1,
                step=0.05,
                effect=_REINDEX,
            ),
        ),
    ),
    SettingSection(
        id="cache",
        page="data",
        title="Önceki cevaplar",
        intro="Aynı ya da aynı anlamdaki soru analiz yerine kayıtlı cevabı alır; sözlük, model "
        "ya da ayar değişince eskiler kullanılmaz.",
        fields=(
            SettingField(
                "cache.enabled",
                "Önceki cevapları kullan",
                "Kapalıyken her soru baştan analiz edilir; cevaplar yine saklanır.",
                "bool",
            ),
            SettingField(
                "cache.meaning",
                "Aynı anlama gelen sorularda da kullan",
                "Kelimesi farklı, kavramı aynı soru (ör. “müşteri no” / “hesap no”); "
                "kapalıyken yalnız aynı kelimeler.",
                "bool",
            ),
            _number(
                "cache.max_age_days",
                "Cevap kaç gün geçerli",
                "Daha eski cevaplar yeniden analiz edilir. 0 = süre sınırı yok.",
                type="int",
                min=0,
                max=365,
                step=1,
                advanced=True,
            ),
        ),
    ),
)

FIELDS: dict[str, SettingField] = {f.key: f for section in SECTIONS for f in section.fields}
# The settings that decide whether a saved answer is used, not what the answer is (Requirement 7).
CACHE_KEYS = frozenset(key for key in FIELDS if key.startswith("cache."))


class SearchSettingsRejected(ValueError):
    """Every refused value of one request, joined as the source joins them (Requirement 3)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SettingValueInvalid(ValueError):
    def __init__(self, reason: SettingRejection, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def _get(settings: Settings, key: str) -> Any:
    current: Any = settings
    for part in key.split("."):
        current = current[part] if isinstance(current, dict) else getattr(current, part)
    return current


def _set(settings: Settings, key: str, value: Any) -> None:
    *path, last = key.split(".")
    current: Any = settings
    for part in path:
        current = current[part] if isinstance(current, dict) else getattr(current, part)
    if isinstance(current, dict):
        current[last] = value
    else:
        setattr(current, last, value)


def values_of(settings: Settings) -> dict[str, Any]:
    """The 24 schema values of engine settings, by key, in schema order."""

    return {key: _get(settings, key) for key in FIELDS}


def defaults() -> dict[str, Any]:
    return values_of(Settings())


def engine_settings(values: Mapping[str, Any]) -> Settings:
    """Engine settings: the measured defaults with the given schema values on top."""

    settings = Settings()
    for key, value in values.items():
        _set(settings, key, value)
    return settings


def check_value(key: str, value: Any) -> bool | int | float:
    """One value against its schema field; the source's Turkish messages (Requirement 3).

    Types are strict (Decision 16): JSON true/false for a switch, a JSON number for a number.
    """

    field = FIELDS.get(key)
    if field is None:
        raise SettingValueInvalid(SettingRejection.UNKNOWN, f"Bilinmeyen ayar: {key}")
    if field.type == "bool":
        if not isinstance(value, bool):
            raise SettingValueInvalid(SettingRejection.TYPE, f"{field.label}: açık/kapalı olmalı")
        return value
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or (isinstance(value, float) and not math.isfinite(value))
    ):
        raise SettingValueInvalid(SettingRejection.TYPE, f"{field.label}: sayı olmalı")
    number: int | float
    if field.type == "int":
        if isinstance(value, float) and not value.is_integer():
            raise SettingValueInvalid(SettingRejection.TYPE, f"{field.label}: tam sayı olmalı")
        number = int(value)
    else:
        number = float(value)
    low, high = field.min, field.max
    if (low is not None and number < low) or (high is not None and number > high):
        raise SettingValueInvalid(
            SettingRejection.RANGE, f"{field.label}: {low} ile {high} arasında olmalı"
        )
    return number


def check_values(submitted: Mapping[str, Any]) -> dict[str, bool | int | float]:
    """Every submitted value checked; all failures in one rejection, nothing partial."""

    checked: dict[str, bool | int | float] = {}
    errors: list[SettingValueInvalid] = []
    for key, value in submitted.items():
        try:
            checked[key] = check_value(key, value)
        except SettingValueInvalid as error:
            errors.append(error)
    if errors:
        unknown = any(e.reason is SettingRejection.UNKNOWN for e in errors)
        raise SearchSettingsRejected(
            "search_setting_unknown" if unknown else "search_setting_invalid",
            "; ".join(e.message for e in errors),
        )
    return checked


def effective_values(stored: Mapping[str, Any]) -> dict[str, Any]:
    """The defaults with the stored (non-default) values on top, in schema order."""

    values = defaults()
    values.update({key: stored[key] for key in FIELDS if key in stored})
    return values


def changed_keys(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    return [key for key in FIELDS if before[key] != after[key]]


def needs_reindex(keys: list[str]) -> bool:
    return any(FIELDS[key].effect is SettingEffect.REINDEX for key in keys)


def settings_digest(values: Mapping[str, Any]) -> str:
    """The content identity of effective values (the settings part of the engine's identity)."""

    blob = json.dumps({key: values[key] for key in FIELDS}, sort_keys=True)
    return hashlib.sha256(blob.encode("ascii")).hexdigest()[:16]


def section_dicts() -> list[dict[str, Any]]:
    """The schema as plain data for the API (Requirement 2)."""

    out = []
    for section in SECTIONS:
        data = {f.name: getattr(section, f.name) for f in fields(section) if f.name != "fields"}
        data["fields"] = [asdict(field) for field in section.fields]
        out.append(data)
    return out
