from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
REAL_DICTIONARY = ROOT / "data" / "DataDictionary-Final.xlsx"

SAMPLE_ROWS = [
    # DAtabaseName is misspelled on purpose — matches the real source file.
    {
        "DAtabaseName": "EDWDM",
        "SchemaName": "CMP",
        "ObjectName": "vCardLimitFullness ",
        "ColumnName": "CardLimitFullnessToday",
        "ColumnDescription": (
            "Kartın bugünkü limit doluluk oranıdır. "
            "Eş anlamlılar/aranabilir terimler: limit doluluk, kart kullanım oranı, "
            "utilization (kart bazlı), fullness."
        ),
        "DatasetGroup": "Kart",
    },
    {
        "DAtabaseName": "EDWDM",
        "SchemaName": "CMP",
        "ObjectName": "vCardLimitFullness",
        "ColumnName": "CustomerPartyId ",
        "ColumnDescription": (
            "[MODEL TAHMİNİ — DOĞRULANMALI] Müşterinin DWH anahtarı. "
            "Eş anlamlılar/aranabilir terimler: müşteri SKEY, party id."
        ),
        "DatasetGroup": None,
    },
    {
        "DAtabaseName": "EDWDM",
        "SchemaName": "CON",
        "ObjectName": "vCreditCardLimit",
        "ColumnName": "CardLimitRatio",
        "ColumnDescription": (
            "[ORİJİNAL AÇIKLAMA HATALIYDI — DÜZELTİLDİ. Kaynakta 'oran' yazıyordu.] "
            "Kart limitinin referans değere oranı. KVKK kapsamında değildir."
        ),
        "DatasetGroup": "Kart",
    },
    # Exact duplicate key -> dropped with a warning.
    {
        "DAtabaseName": "EDWDM",
        "SchemaName": "CMP",
        "ObjectName": "vCardLimitFullness",
        "ColumnName": "CardLimitFullnessToday",
        "ColumnDescription": "Tekrar.",
        "DatasetGroup": "Kart",
    },
]

SAMPLE_QUALITY = [
    {
        "Kategori": "İsimlendirme/İçerik Uyumsuzluğu",
        "ObjectName": "vCreditCardLimit",
        "ColumnName": "CardLimitRatio",
        "Bulgu": "Ad oran diyor, içerik farklı.",
        "Öneri": "Doğrulanmalı.",
    },
    {
        "Kategori": "Yazım Hatası",
        "ObjectName": "vCardLimitFullness",
        "ColumnName": "CardLimitFullnessToday",
        "Bulgu": "Yazım hatası.",
        "Öneri": "-",
    },
]


@pytest.fixture
def sample_dictionary_path(tmp_path: Path) -> Path:
    path = tmp_path / "dictionary.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(SAMPLE_ROWS).to_excel(writer, sheet_name="Sheet1", index=False)
        pd.DataFrame(SAMPLE_QUALITY).to_excel(writer, sheet_name="Sheet2", index=False)
    return path


@pytest.fixture
def real_dictionary_path() -> Path:
    if not REAL_DICTIONARY.exists():
        pytest.skip("Gerçek sözlük yok (data/ gitignore'da)")
    return REAL_DICTIONARY
