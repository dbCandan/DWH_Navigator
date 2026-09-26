"""Editable settings for the settings screen: labels, help, types, ranges, effects.

The schema is the single list of what the screen may change. Values are read from and
written to the ``Settings`` dataclasses by dotted path (``"llm.temperature"``).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from vsa.config import Settings
from vsa.text.normalize import fold

# effect: when does a change take hold?
NOW = "anında"  # engine is rebuilt from the index on save (seconds)
REINDEX = "indeks"  # BM25 index must be rebuilt (button on the screen, ~10 s)
DENSE = "vektör"  # dense index must be rebuilt (`vsa index --dense`, ~45 min on CPU)

SECTIONS: list[dict[str, Any]] = [
    {
        "id": "llm",
        "title": "Yapay zekâ hakemi",
        "intro": "Aday tabloları okuyup gerekçe yazan ve sıralamaya katkı veren yerel dil modeli "
        "(HANDOVER §10). Kapalıysa uygulama kural tabanlı çalışır.",
        "fields": [
            {
                "key": "llm.enabled",
                "label": "LLM katmanı açık",
                "type": "bool",
                "effect": NOW,
                "help": "Hakem ve LLM sorgu genişletme bu anahtara bağlı. Vektör araması bundan bağımsızdır.",
            },
            {
                "key": "llm.endpoint",
                "label": "Model sunucusu adresi",
                "type": "str",
                "effect": NOW,
                "help": "OpenAI uyumlu uç nokta (LM Studio, vLLM, llama.cpp, Ollama). "
                "Windows'ta 'localhost' yerine 127.0.0.1 kullanılır.",
            },
            {
                "key": "llm.model",
                "label": "Hakem modeli",
                "type": "model",
                "kind": "chat",
                "effect": NOW,
                "help": "Aday listesinden seçim yapan sohbet modeli. Bkz. aşağıdaki ölçüm sonuçları.",
            },
            {
                "key": "llm.temperature",
                "label": "Sıcaklık",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "0: her seferinde aynı cevap (tutarlılık). Yükseldikçe çeşitlilik ve "
                "tutarsızlık artar.",
            },
            {
                "key": "llm.reasoning_effort",
                "label": "Düşünme modu",
                "type": "select",
                "effect": NOW,
                "options": [
                    ["none", "Kapalı (doğrudan cevap)"],
                    ["low", "Düşük"],
                    ["medium", "Orta"],
                    ["high", "Yüksek"],
                    ["", "Gönderme (model varsayılanı)"],
                ],
                "help": "Düşünen modeller (Qwen3.x) için. Kapalı değilse cevap çok uzar; qwen3.5 düşünmede "
                "tüm bütçeyi harcayıp boş dönebiliyor (ADR-021).",
            },
            {
                "key": "llm.judge",
                "label": "Hakem sıralamaya katılsın",
                "type": "bool",
                "effect": NOW,
                "help": "Kapalıysa LLM çağrılmaz (Soru sor ~0,1 sn), gerekçeler kural tabanlı yazılır.",
            },
            {
                "key": "llm.judge_candidates",
                "label": "Hakeme gösterilen tablo sayısı",
                "type": "int",
                "min": 2,
                "max": 15,
                "step": 1,
                "effect": NOW,
                "help": "Daha fazla aday = daha uzun istem = daha yavaş cevap.",
            },
            {
                "key": "llm.timeout",
                "label": "Zaman aşımı (sn)",
                "type": "int",
                "min": 10,
                "max": 1800,
                "step": 10,
                "effect": NOW,
                "help": "Süre dolarsa kural tabanlı sonuç döner (ADR-008).",
            },
            {
                "key": "llm.expand_query",
                "label": "LLM ile sorgu genişletme",
                "type": "bool",
                "effect": NOW,
                "help": "Her soruya ek bir LLM çağrısı; terimler yalnız BM25 aday havuzunu genişletir (§7.2c).",
            },
            {
                "key": "llm.api_key",
                "label": "API anahtarı",
                "type": "secret",
                "effect": NOW,
                "help": "Yalnız sunucu anahtar istiyorsa. Boş bırakılırsa mevcut anahtar korunur.",
            },
        ],
    },
    {
        "id": "cloud",
        "title": "Bulut modelleri (yalnız ölçüm)",
        "intro": "NVIDIA API kataloğundaki (build.nvidia.com) modelleri Model laboratuvarında ölçmek için. "
        "Uygulamanın hakemi yerelde kalır; bu ayar yalnız ölçüme etki eder. Ölçüm sırasında test soruları "
        "ile aday tabloların adları, kolon adları ve açıklamaları kurum dışına gönderilir (ADR-026).",
        "fields": [
            {
                "key": "cloud.enabled",
                "label": "Bulut ölçümü açık",
                "type": "bool",
                "effect": NOW,
                "help": "Kapalıyken laboratuvar bulut modellerini listelemez ve hiçbir istek dışarı çıkmaz.",
            },
            {
                "key": "cloud.api_key",
                "label": "API anahtarı",
                "type": "secret",
                "effect": NOW,
                "help": "build.nvidia.com → bir model → 'Get API Key' (nvapi-… ile başlar). Boş bırakılırsa "
                "kayıtlı anahtar korunur; NVIDIA_API_KEY ortam değişkeni de kullanılabilir.",
            },
            {
                "key": "cloud.endpoint",
                "label": "API adresi",
                "type": "str",
                "effect": NOW,
                "help": "OpenAI uyumlu uç nokta. Varsayılan NVIDIA: https://integrate.api.nvidia.com/v1",
            },
            {
                "key": "cloud.rpm",
                "label": "Dakikadaki istek sınırı",
                "type": "int",
                "min": 1,
                "max": 120,
                "step": 1,
                "effect": NOW,
                "help": "Ücretsiz katman dakikada ~40 istek tanır; sınır aşılırsa istemci bekleyip yeniden dener.",
            },
        ],
    },
    {
        "id": "dense",
        "title": "Anlamsal arama",
        "intro": "Kelimesi farklı ama anlamı yakın kolonları bulan vektör araması (M3, ADR-019).",
        "fields": [
            {
                "key": "dense.enabled",
                "label": "Anlamsal arama açık",
                "type": "bool",
                "effect": NOW,
                "help": "Vektör indeksi yoksa uyarı verir ve yalnız BM25 ile çalışır.",
            },
            {
                "key": "llm.embedding_model",
                "label": "Embedding modeli",
                "type": "model",
                "kind": "embedding",
                "effect": DENSE,
                "help": "Değişirse vektör indeksi yeniden kurulmalı (vsa index --dense).",
            },
            {
                "key": "dense.weight",
                "label": "Anlamsal benzerlik ağırlığı",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Kolon arama skorunda vektör benzerliğinin payı; kalanı BM25.",
            },
            {
                "key": "dense.top_k",
                "label": "Vektör aday kolon sayısı",
                "type": "int",
                "min": 20,
                "max": 1000,
                "step": 10,
                "effect": NOW,
                "help": "Aday havuzuna eklenen en benzer kolon sayısı.",
            },
        ],
    },
    {
        "id": "scoring",
        "title": "Skorlama",
        "intro": "Kural skoru, LLM katkısı ve eşikler (§8, §9, ADR-022). Değiştirmeden önce ve sonra "
        "`vsa eval --save` çalıştırın.",
        "fields": [
            {
                "key": "scoring.w_rule",
                "label": "Kural ağırlığı",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Nihai skor = (w_kural × kural + w_LLM × LLM) / toplam.",
            },
            {
                "key": "scoring.w_llm",
                "label": "LLM ağırlığı",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "0,4'te hakem sıralamayı bozuyordu; 0,25 ölçümle seçildi.",
            },
            {
                "key": "scoring.min_candidate_score",
                "label": "Gösterilecek en düşük skor",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Altındaki adaylar hiç gösterilmez.",
            },
            {
                "key": "scoring.min_answer_score",
                "label": "Cevap eşiği",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "En iyi aday bunun altındaysa cevap BULUNAMADI (ADR-006).",
            },
            {
                "key": "scoring.min_answer_coverage",
                "label": "Cevap için kavram kapsaması",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "En iyi tablo talebin bilgi içeriğinin bu kadarını karşılamalı (ADR-013).",
            },
            {
                "key": "scoring.object.best_column",
                "label": "Tablo skoru: en iyi kolon",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "§8 obje skoru bileşeni.",
            },
            {
                "key": "scoring.object.coverage",
                "label": "Tablo skoru: kavram kapsaması",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "§8 obje skoru bileşeni.",
            },
            {
                "key": "scoring.object.time",
                "label": "Tablo skoru: zaman boyutu",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Talepte zaman yoksa hesaba katılmaz (ADR-011).",
            },
            {
                "key": "scoring.object.granularity",
                "label": "Tablo skoru: müşteri seviyesi",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Müşteri bazlı talepte uygulanır.",
            },
            {
                "key": "scoring.flag_penalty.model_estimated",
                "label": "Ceza çarpanı: model tahmini açıklama",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "§9.2 (×0,85).",
            },
            {
                "key": "scoring.flag_penalty.naming_mismatch",
                "label": "Ceza çarpanı: isim/içerik uyumsuzluğu",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "§9.2 (×0,90).",
            },
        ],
    },
    {
        "id": "search",
        "title": "Arama",
        "intro": "BM25 kelime araması ve aday havuzu (§6.6, ADR-015).",
        "fields": [
            {
                "key": "search.top_k_columns",
                "label": "Kolon aday havuzu",
                "type": "int",
                "min": 20,
                "max": 1000,
                "step": 10,
                "effect": NOW,
                "help": "BM25'ten alınan en iyi kolon sayısı.",
            },
            {
                "key": "search.candidate_object_columns",
                "label": "Obje adayı için taranan kolon",
                "type": "int",
                "min": 50,
                "max": 3000,
                "step": 50,
                "effect": NOW,
                "help": "Kavramları birlikte karşılayan tabloların kaçmaması için geniş tutulur.",
            },
            {
                "key": "search.top_k_objects",
                "label": "Sıralanan tablo sayısı",
                "type": "int",
                "min": 3,
                "max": 50,
                "step": 1,
                "effect": NOW,
                "help": "Soru başına değerlendirilen en iyi tablo sayısı.",
            },
            {
                "key": "search.field_weights.name",
                "label": "Alan ağırlığı: kolon adı",
                "type": "float",
                "min": 0,
                "max": 10,
                "step": 0.5,
                "effect": REINDEX,
                "help": "§6.6 (3).",
            },
            {
                "key": "search.field_weights.synonyms",
                "label": "Alan ağırlığı: eş anlamlılar",
                "type": "float",
                "min": 0,
                "max": 10,
                "step": 0.5,
                "effect": REINDEX,
                "help": "§6.6 (2).",
            },
            {
                "key": "search.field_weights.description",
                "label": "Alan ağırlığı: açıklama",
                "type": "float",
                "min": 0,
                "max": 10,
                "step": 0.5,
                "effect": REINDEX,
                "help": "§6.6 (1).",
            },
            {
                "key": "search.field_weights.object",
                "label": "Alan ağırlığı: tablo adı",
                "type": "float",
                "min": 0,
                "max": 10,
                "step": 0.5,
                "effect": REINDEX,
                "help": "§6.6 (1).",
            },
            {
                "key": "search.bm25.k1",
                "label": "BM25 k1",
                "type": "float",
                "min": 0.1,
                "max": 3,
                "step": 0.1,
                "effect": REINDEX,
                "help": "Terim frekansı doygunluğu.",
            },
            {
                "key": "search.bm25.b",
                "label": "BM25 b",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": REINDEX,
                "help": "Belge uzunluğu normalizasyonu.",
            },
        ],
    },
    {
        "id": "expansion",
        "title": "Sorgu genişletme",
        "intro": "Kurumsal terim sözlüğü ve sözlüğün kendi eş anlamlıları (§7).",
        "fields": [
            {
                "key": "expansion.enabled",
                "label": "Kurumsal terim sözlüğü",
                "type": "bool",
                "effect": NOW,
                "help": "config/term_dictionary.csv — katılım bankacılığı terimleri.",
            },
            {
                "key": "expansion.synonyms",
                "label": "Sözlük eş anlamlıları",
                "type": "bool",
                "effect": NOW,
                "help": "Açıklamalardaki 'Eş anlamlılar/aranabilir terimler' bölümü.",
            },
            {
                "key": "expansion.weight",
                "label": "Genişletme terimi ağırlığı",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "effect": NOW,
                "help": "Özgün sorgu terimleri 1,0 ağırlık alır.",
            },
        ],
    },
    {
        "id": "files",
        "title": "Dosyalar",
        "intro": "Sözlük, indeks ve rapor konumları. Sözlük veya durak kelimeler değişirse indeks "
        "yeniden kurulmalı.",
        "fields": [
            {
                "key": "dictionary.path",
                "label": "Veri sözlüğü",
                "type": "str",
                "effect": REINDEX,
                "help": "Excel dosyası (Sheet1: kolonlar).",
            },
            {
                "key": "dictionary.sheet",
                "label": "Kolon sayfası",
                "type": "str",
                "effect": REINDEX,
                "help": "",
            },
            {
                "key": "dictionary.quality_sheet",
                "label": "Kalite bulguları sayfası",
                "type": "str",
                "effect": REINDEX,
                "help": "Opsiyonel; boş bırakılabilir.",
            },
            {
                "key": "expansion.term_dictionary",
                "label": "Terim sözlüğü",
                "type": "str",
                "effect": NOW,
                "help": "CSV: term,equivalents,domain,note.",
            },
            {
                "key": "expansion.stopwords",
                "label": "Durak kelimeler",
                "type": "str",
                "effect": REINDEX,
                "help": "Satır başına bir kelime.",
            },
            {
                "key": "index.dir",
                "label": "İndeks klasörü",
                "type": "str",
                "effect": REINDEX,
                "help": "",
            },
            {
                "key": "report.out_dir",
                "label": "Rapor klasörü",
                "type": "str",
                "effect": NOW,
                "help": "Excel raporlarının yazıldığı yer.",
            },
        ],
    },
]

FIELDS = {f["key"]: f for sec in SECTIONS for f in sec["fields"]}
SECRET_KEYS = [k for k, f in FIELDS.items() if f["type"] == "secret"]


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
    out = {k: get_path(raw, k) for k in FIELDS}
    for key in SECRET_KEYS:
        out[key] = ""  # never sent to the browser
    return out


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
    return str(value).strip()  # str, model, secret


def to_yaml_tree(values: dict[str, Any]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for key, value in values.items():
        if key == "dictionary.quality_sheet" and value == "":
            value = None
        set_path(tree, key, value)
    return tree


# Hosted catalogs list every kind of model; the lab only wants text chat models.
NON_CHAT = (
    "embed", "rerank", "reward", "guard", "safety", "clip", "parse", "retriever", "-vl",
    "vision", "vila", "neva", "kosmos", "fuyu", "paligemma", "deplot", "cosmos", "tts",
    "asr", "whisper", "riva", "detector", "pii", "usdcode", "usdsearch", "bge", "e5-",
    "sdxl", "flux", "stable-diffusion", "audio", "speech", "ocr", "esm", "molmim", "genmol",
    "diffdock", "alphafold", "openfold", "proteinmpnn", "rfdiffusion", "streampetr",
    "content-safety", "topic-control", "jailbreak", "calibration", "translate",
)


def is_chat_model(model_id: str) -> bool:
    folded = fold(model_id)
    return not any(k in folded for k in NON_CHAT)
