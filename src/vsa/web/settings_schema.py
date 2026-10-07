"""Editable settings for the settings screen: labels, help, types, ranges, effects.

The schema is the single list of what the screen may change, grouped into pages and
sections in plain language; rarely touched fields are marked ``advanced``. The model
connection is not here: it is the LLM integrations page (ADR-032). Values are read from
and written to the ``Settings`` dataclasses by dotted path (``"analyst.shortlist"``).
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
        "intro": "Analistin ne kadar malzeme okuyacağını ve ona verilen arama ipuçlarını belirler.",
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
        "id": "analyst",
        "page": "search",
        "title": "Analist",
        "intro": "Cevabı sohbet modeli yazar (ADR-038). Önce bütün tablo kataloğundan aday "
        "seçer, sonra adayların kolonlarını okur. Okunan malzeme büyüdükçe cevap yavaşlar.",
        "fields": [
            {
                "key": "analyst.shortlist",
                "label": "Kolonları okunacak aday tablo sayısı",
                "type": "int",
                "min": 3,
                "max": 30,
                "step": 1,
                "effect": NOW,
                "help": "1. adımda modelin seçebileceği en fazla tablo.",
            },
            {
                "key": "analyst.detail_columns",
                "label": "Tam açıklamasıyla okunan kolon sayısı (tablo başına)",
                "type": "int",
                "min": -1,
                "max": 60,
                "step": 1,
                "effect": NOW,
                "help": "Talebe en ilgili bu kadar kolon tam sözlük açıklamasıyla, diğerleri "
                "“Ad [Rol]: özet” olarak gider. -1: hepsi tam açıklamayla (yavaş).",
            },
            {
                "key": "analyst.min_confidence",
                "label": "Gösterilecek en düşük model güveni",
                "type": "float",
                "format": "pct",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Modelin bundan az emin olduğu tablolar önerilmez (“bulunamadı” geçerli cevap).",
            },
            {
                "key": "analyst.catalog_chunks",
                "label": "Katalog kaç parçada okunur",
                "type": "int",
                "min": 1,
                "max": 8,
                "step": 1,
                "effect": NOW,
                "advanced": True,
                "help": "1: tek çağrı (hızlı, önek önbelleğine uygun). N: N parça paralel okunur, "
                "adaylar sonra yan yana kıyaslanır.",
            },
            {
                "key": "analyst.catalog_columns",
                "label": "Katalogda kolon adları da olsun",
                "type": "bool",
                "effect": NOW,
                "advanced": True,
                "help": "Kapalıyken katalog tablo açıklaması, satır düzeyi ve zaman kolonlarından "
                "oluşur (~43 bin token); açıkken kolon adları da eklenir (çok daha uzun).",
            },
            {
                "key": "analyst.max_tokens",
                "label": "Cevap için en fazla token",
                "type": "int",
                "min": 1000,
                "max": 32000,
                "step": 500,
                "effect": NOW,
                "advanced": True,
                "help": "2. adımda modelin yazabileceği en uzun cevap.",
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
        "title": "Kural ipuçları (tablo sıralaması)",
        "intro": "Kural motoru cevap yazmaz; modele “kural skoru en yüksek tablolar” ipucunu "
        "hazırlar. Bir tablonun kural puanı beş parçadan oluşur. Değiştirmeden önce ve sonra "
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
                "key": "search.top_k_objects",
                "label": "Değerlendirilen tablo sayısı",
                "type": "int",
                "min": 3,
                "max": 50,
                "step": 1,
                "effect": NOW,
                "help": "Soru başına kural motorunun sıraladığı tablo sayısı (ipucu havuzu).",
            },
            {
                "key": "scoring.min_candidate_score",
                "label": "İpucu listesine girecek en düşük kural puanı",
                "type": "float",
                "format": "pct",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Bunun altındaki tablolar modele ipucu olarak gösterilmez.",
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
        # Shown on the admin screen's Sözlük view, next to the source switch (ADR-049), not
        # on a settings page: "dictionary" is not one of PAGES.
        "id": "dictionary",
        "page": "dictionary",
        "title": "Dosya ayarları",
        "intro": "Sözlük dosyalarının yerleri. Bir dosya değişirse indeks yeniden kurulmalı.",
        "fields": [
            {
                "key": "dictionary.store",
                "label": "Sözlük dosyası",
                "type": "str",
                "effect": REINDEX,
                "help": "İçe aktarılan sözlüğün saklandığı yer (data/dictionary.jsonl).",
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
    return str(value).strip()


def to_yaml_tree(values: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """The screen's values written over ``base`` (the settings file as it is), so keys the
    screen does not show — the model connection under ``llm:`` — survive."""
    tree: dict[str, Any] = copy.deepcopy(base or {})
    for key, value in values.items():
        set_path(tree, key, value)
    return tree
