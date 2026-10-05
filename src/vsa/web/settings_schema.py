"""Editable settings for the settings screen: labels, help, types, ranges, effects.

The schema is the single list of what the screen may change, grouped into pages and
sections in plain language; rarely touched fields are marked ``advanced``. The model
connection is not here: it is the LLM integrations page (ADR-032). Values are read from
and written to the ``Settings`` dataclasses by dotted path (``"scoring.min_answer_score"``).
"""

from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any

from vsa.config import Settings

# effect: when does a change take hold?
NOW = "anında"  # engine is rebuilt from the index on save (seconds)
REINDEX = "indeks"  # BM25 index must be rebuilt (button on the screen, ~10 s)

# Pages of the settings screen, in order. The LLM page is drawn from /api/llm, not from fields.
PAGES: list[dict[str, Any]] = [
    {
        "id": "llm",
        "title": "Yapay zekâ",
        "intro": "Talebi okuyup cevabı yazan sohbet modeli.",
    },
    {
        "id": "search",
        "title": "Arama ve cevap",
        "intro": "Hangi tablonun önerileceğini ve ne zaman “bulunamadı” deneceğini belirler.",
    },
    {
        "id": "data",
        "title": "Veri ve bakım",
        "intro": "Veri sözlüğü, indeks ve rapor konumları; indeksin yeniden kurulması.",
    },
]

# ``advanced`` fields sit behind "Uzman ayarları"; a section that is all advanced is folded
# as a whole. ``format: pct`` shows a 0–1 value as a percentage.
SECTIONS: list[dict[str, Any]] = [
    {
        "id": "answer",
        "page": "search",
        "title": "Cevap ne zaman verilir?",
        "intro": "Uygulama emin olmadığı tabloyu önermez; eşiği geçen bir tablo yoksa "
        "“bulunamadı” der. Eşikleri yükseltmek daha az ama daha kesin öneri demektir.",
        "fields": [
            {
                "key": "scoring.min_answer_score",
                "label": "Cevap vermek için gereken güven",
                "type": "float",
                "format": "pct",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "En iyi tablonun güveni bunun altındaysa cevap “bulunamadı” olur.",
            },
            {
                "key": "scoring.min_candidate_score",
                "label": "Listede gösterilecek en düşük güven",
                "type": "float",
                "format": "pct",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Bunun altındaki tablolar hiç listelenmez.",
            },
            {
                "key": "scoring.min_answer_coverage",
                "label": "Talebin ne kadarı karşılanmalı",
                "type": "float",
                "format": "pct",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "advanced": True,
                "help": "En iyi tablo, talepteki kavramların (nadir olanlar daha ağır sayılır) en "
                "az bu kadarını taşımalı.",
            },
        ],
    },
    {
        "id": "terms",
        "page": "search",
        "title": "Eş anlamlılar ve terimler",
        "intro": "İş biriminin kelimeleriyle sözlüğün kelimeleri arasında köprü kurar: “kredi” "
        "arayan “fon kullandırım”ı da bulur.",
        "fields": [
            {
                "key": "expansion.enabled",
                "label": "Kurumsal terim sözlüğünü kullan",
                "type": "bool",
                "effect": NOW,
                "help": "Katılım bankacılığı terimleri ve kısaltmalar (config/term_dictionary.csv).",
            },
            {
                "key": "expansion.synonyms",
                "label": "Sözlüğün eş anlamlılarını kullan",
                "type": "bool",
                "effect": NOW,
                "help": "Kolon açıklamalarındaki “Eş anlamlılar / aranabilir terimler” bölümleri.",
            },
            {
                "key": "expansion.weight",
                "label": "Eş anlamlı terimlerin ağırlığı",
                "type": "float",
                "format": "pct",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "advanced": True,
                "help": "Kullanıcının kendi yazdığı kelimeler %100 sayılır.",
            },
        ],
    },
    {
        "id": "ranking",
        "page": "search",
        "advanced": True,
        "title": "Tablo sıralaması",
        "intro": "Bir tablonun puanı beş parçadan oluşur. Değiştirmeden önce ve sonra "
        "`vsa eval --save` ile ölçün.",
        "fields": [
            {
                "key": "scoring.object.best_column",
                "label": "En iyi eşleşen kolon",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Tablodaki en iyi kolonun talebe uyumu.",
            },
            {
                "key": "scoring.object.coverage",
                "label": "Kavramları birlikte taşıma",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Talepteki kavramların kaçı aynı tabloda.",
            },
            {
                "key": "scoring.object.topic",
                "label": "Konu uyumu",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Tablonun bütün olarak talebin konusu olması; çok geniş tabloları dengeler.",
            },
            {
                "key": "scoring.object.time",
                "label": "Zaman kolonu",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "“Aylık”, “günlük” istenirse dönem/tarih kolonu var mı. İstenmezse sayılmaz.",
            },
            {
                "key": "scoring.object.granularity",
                "label": "Müşteri seviyesi",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Müşteri bazlı talepte müşteri anahtarı var mı.",
            },
            {
                "key": "scoring.flag_penalty.model_estimated",
                "label": "Doğrulanmamış açıklama cezası",
                "type": "float",
                "format": "pct",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Açıklaması “model tahmini” olan kolonun puanı bu orana iner.",
            },
            {
                "key": "scoring.flag_penalty.naming_mismatch",
                "label": "Ad/içerik uyumsuzluğu cezası",
                "type": "float",
                "format": "pct",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Kalite bulgularında adı içeriğiyle uyuşmayan kolonun puanı bu orana iner.",
            },
            {
                "key": "search.top_k_objects",
                "label": "Değerlendirilen tablo sayısı",
                "type": "int",
                "min": 3,
                "max": 50,
                "step": 1,
                "effect": NOW,
                "help": "Soru başına sıralanan en iyi tablo sayısı.",
            },
        ],
    },
    {
        "id": "words",
        "page": "search",
        "advanced": True,
        "title": "Kelime araması",
        "intro": "Kolon adları, eş anlamlılar ve açıklamalar üzerinde BM25 araması. Alan "
        "ağırlıkları ve BM25 değerleri indekse gömülüdür; değişince indeks yeniden kurulur.",
        "fields": [
            {
                "key": "search.field_weights.name",
                "label": "Kolon adı ağırlığı",
                "type": "float",
                "min": 0,
                "max": 10,
                "step": 0.5,
                "effect": REINDEX,
                "help": "",
            },
            {
                "key": "search.field_weights.synonyms",
                "label": "Eş anlamlılar ağırlığı",
                "type": "float",
                "min": 0,
                "max": 10,
                "step": 0.5,
                "effect": REINDEX,
                "help": "",
            },
            {
                "key": "search.field_weights.description",
                "label": "Açıklama ağırlığı",
                "type": "float",
                "min": 0,
                "max": 10,
                "step": 0.5,
                "effect": REINDEX,
                "help": "",
            },
            {
                "key": "search.field_weights.object",
                "label": "Tablo adı ağırlığı",
                "type": "float",
                "min": 0,
                "max": 10,
                "step": 0.5,
                "effect": REINDEX,
                "help": "",
            },
            {
                "key": "search.top_k_columns",
                "label": "Aday kolon sayısı",
                "type": "int",
                "min": 20,
                "max": 1000,
                "step": 10,
                "effect": NOW,
                "help": "Kelime aramasından alınan en iyi kolon sayısı.",
            },
            {
                "key": "search.candidate_object_columns",
                "label": "Aday tablo için taranan kolon",
                "type": "int",
                "min": 50,
                "max": 3000,
                "step": 50,
                "effect": NOW,
                "help": "Kavramları birlikte taşıyan tablolar kaçmasın diye geniş tutulur.",
            },
            {
                "key": "search.bm25.k1",
                "label": "BM25 k1",
                "type": "float",
                "min": 0.1,
                "max": 3,
                "step": 0.1,
                "effect": REINDEX,
                "help": "Aynı kelimenin tekrarı ne kadar sayılsın.",
            },
            {
                "key": "search.bm25.b",
                "label": "BM25 b",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": REINDEX,
                "help": "Uzun açıklamalar ne kadar dengelensin.",
            },
        ],
    },
    {
        "id": "dictionary",
        "page": "data",
        "title": "Veri sözlüğü",
        "intro": "Uygulamanın aradığı kaynak. Dosya değişirse indeks yeniden kurulmalı.",
        "fields": [
            {
                "key": "dictionary.path",
                "label": "Sözlük dosyası",
                "type": "str",
                "effect": REINDEX,
                "help": "Excel dosyası (data/VeriSozlugu.xlsx); kolonlar Kolonlar sayfasında.",
            },
            {
                "key": "dictionary.sheet",
                "label": "Kolon sayfası",
                "type": "str",
                "effect": REINDEX,
                "advanced": True,
                "help": "",
            },
            {
                "key": "dictionary.quality_sheet",
                "label": "Kalite bulguları sayfası",
                "type": "str",
                "effect": REINDEX,
                "advanced": True,
                "help": "İsteğe bağlı; boş bırakılabilir.",
            },
            {
                "key": "expansion.term_dictionary",
                "label": "Terim sözlüğü dosyası",
                "type": "str",
                "effect": NOW,
                "advanced": True,
                "help": "CSV: term, equivalents, domain, note.",
            },
            {
                "key": "expansion.stopwords",
                "label": "Durak kelimeler dosyası",
                "type": "str",
                "effect": REINDEX,
                "advanced": True,
                "help": "Aramada yok sayılan kelimeler, satır başına bir tane.",
            },
        ],
    },
    {
        "id": "cache",
        "page": "data",
        "title": "Önceki cevaplar",
        "intro": "Analistin yazdığı cevaplar saklanır. Aynı soru ya da terim sözlüğüne göre aynı "
        "anlama gelen bir soru yeniden sorulunca dakikalarca analiz yerine kayıtlı cevap gelir. "
        "Sözlük, model veya cevabı etkileyen bir ayar değişince eski cevaplar kullanılmaz.",
        "fields": [
            {
                "key": "cache.enabled",
                "label": "Önceki cevapları kullan",
                "type": "bool",
                "effect": NOW,
                "help": "Kapalıyken her soru baştan analiz edilir; cevaplar yine saklanır.",
            },
            {
                "key": "cache.meaning",
                "label": "Aynı anlama gelen sorularda da kullan",
                "type": "bool",
                "effect": NOW,
                "help": "Kelimeleri farklı ama kavramları aynı soru (ör. “müşteri no” / “hesap "
                "no”). Kapalıyken yalnız aynı kelimelerle sorulan soru.",
            },
            {
                "key": "cache.max_age_days",
                "label": "Cevap kaç gün geçerli",
                "type": "int",
                "min": 0,
                "max": 365,
                "step": 1,
                "effect": NOW,
                "advanced": True,
                "help": "Daha eski cevaplar yeniden analiz edilir. 0 = süre sınırı yok.",
            },
        ],
    },
    {
        "id": "places",
        "page": "data",
        "title": "Klasörler",
        "intro": "",
        "fields": [
            {
                "key": "report.out_dir",
                "label": "Rapor klasörü",
                "type": "str",
                "effect": NOW,
                "help": "İndirilen Excel raporları buraya da yazılır.",
            },
            {
                "key": "index.dir",
                "label": "İndeks klasörü",
                "type": "str",
                "effect": REINDEX,
                "advanced": True,
                "help": "",
            },
        ],
    },
]

FIELDS = {f["key"]: f for sec in SECTIONS for f in sec["fields"]}


def get_path(data: dict[str, Any], key: str) -> Any:
    for part in key.split("."):
        data = data[part]
    return data


def set_path(data: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    for part in parts[:-1]:
        data = data.setdefault(part, {})
    data[parts[-1]] = value


def values_of(settings: Settings) -> dict[str, Any]:
    raw = asdict(settings)
    return {k: get_path(raw, k) for k in FIELDS}


def defaults() -> dict[str, Any]:
    return values_of(Settings())


def coerce(key: str, value: Any) -> Any:
    """Validate one submitted value against the schema; raises ValueError in Turkish."""
    f = FIELDS.get(key)
    if f is None:
        raise ValueError(f"Bilinmeyen ayar: {key}")
    kind = f["type"]
    label = f["label"]
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{label}: açık/kapalı olmalı")
        return value
    if kind in ("int", "float"):
        try:
            num = int(value) if kind == "int" else float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}: sayı olmalı") from exc
        if kind == "int" and float(value) != num:
            raise ValueError(f"{label}: tam sayı olmalı")
        lo, hi = f.get("min"), f.get("max")
        if (lo is not None and num < lo) or (hi is not None and num > hi):
            raise ValueError(f"{label}: {lo} ile {hi} arasında olmalı")
        return num
    if kind == "select":
        allowed = [o[0] for o in f["options"]]
        if value not in allowed:
            raise ValueError(f"{label}: geçersiz seçim")
        return value
    return str(value).strip()


def to_yaml_tree(values: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """The screen's values written over ``base`` (the settings file as it is), so keys the
    screen does not show — the model connection under ``llm:`` / ``analyst:`` — survive."""
    tree: dict[str, Any] = copy.deepcopy(base or {})
    for key, value in values.items():
        if key == "dictionary.quality_sheet" and value == "":
            value = None
        set_path(tree, key, value)
    return tree
