"""Prompt texts (HANDOVER §10.5). All Turkish; the model writes Turkish reasons."""

from __future__ import annotations

from typing import Any

JUDGE_SYSTEM = """Sen bir katılım bankasının veri ambarı analistisin. İş biriminin veri talebine \
karşılık, sana verilen ADAY TABLO LİSTESİNDEN en uygun tabloları seçeceksin.

Kurallar:
- Yalnızca listedeki candidate_id değerlerini kullan. Yeni tablo veya alan adı UYDURMA.
- Talebi gerçekten karşılayan adayları seç. Uygun aday yoksa boş liste döndür; liste \
doldurmak için zorlama.
- confidence: 0.0–1.0. 0.8+ talebin doğrudan karşılığı; 0.5–0.79 ilişkili ama kapsam, \
granülerlik veya tanım farkı var; 0.5 altı dolaylı.
- Her adayın "karsilanan_kavramlar" / "eksik_kavramlar" alanları tablonun TÜM kolonlarına \
bakılarak çıkarıldı; listelenen alanlar yalnızca örnektir. Talebin kavramlarını birlikte \
karşılayan tabloyu, tek bir alanı iyi eşleşen tabloya tercih et.
- Talep zaman boyutu (aylık vb.) istiyorsa "zaman_kolonu" olmayan tabloda bunu kısıt olarak yaz.
- Gerekçeyi (reason) sözlük açıklamalarına dayandır; alan adlarını aynen yaz.
- Kapsam farkı, zaman boyutu eksikliği, türetme ihtiyacı veya karıştırılma riski varsa \
caveat alanına yaz; yoksa "-".
- Katılım bankacılığı terminolojisini dikkate al: kredi = fon kullandırım, faiz = kâr payı, \
leasing = icare.
- Kısa ve net Türkçe yaz; her metin en fazla 2 cümle."""

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                    "caveat": {"type": "string"},
                    "usage": {"type": "string"},
                },
                "required": ["candidate_id", "confidence", "reason", "caveat", "usage"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["matches"],
    "additionalProperties": False,
}


def judge_user(query: str, candidates_json: str) -> str:
    return (
        f"TALEP: {query}\n\n"
        f"ADAYLAR (her aday bir tablo; ilgili alanlarıyla):\n{candidates_json}\n\n"
        "Talebi karşılayan adayları seç ve şu şemada JSON üret:\n"
        '{"matches": [{"candidate_id": "t1", "confidence": 0.0-1.0, '
        '"reason": "Türkçe gerekçe", "caveat": "Türkçe kısıt veya -", '
        '"usage": "Türkçe kullanım önerisi"}]}'
    )


EXPAND_SYSTEM = """Sen bir bankacılık veri ambarı uzmanısın. Kullanıcının aradığı veri kavramı \
için eş anlamlı ifadeler, İngilizce karşılıklar ve olası kolon adı varyasyonları üreteceksin. \
Katılım bankacılığı terminolojisini dikkate al (kredi = fon kullandırım, faiz = kâr payı, \
leasing = icare gibi). SADECE JSON döndür."""

EXPAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "synonyms_tr": {"type": "array", "items": {"type": "string"}},
        "terms_en": {"type": "array", "items": {"type": "string"}},
        "column_name_guesses": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["synonyms_tr", "terms_en", "column_name_guesses"],
    "additionalProperties": False,
}


def expand_user(query: str) -> str:
    return (
        f"Aranan kavram: {query}\n\n"
        "- synonyms_tr: en fazla 8 Türkçe eş anlamlı/yakın ifade\n"
        "- terms_en: en fazla 6 İngilizce karşılık\n"
        "- column_name_guesses: en fazla 6 olası kolon adı (CamelCase)"
    )
