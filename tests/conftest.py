from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
REAL_DICTIONARY = ROOT / "data" / "VeriSozlugu.xlsx"

SAMPLE_ROWS = [
    # DAtabaseName is misspelled on purpose — an older source file spelt it so.
    {
        "DAtabaseName": "EDWDM",
        "SchemaName": "CMP",
        "ObjectName": "vCardLimitFullness ",
        "ColumnName": "CardLimitFullnessToday",
        "ColumnDescription": "Kartın bugünkü limit doluluk oranıdır.",
        "Synonyms": "limit doluluk, kart kullanım oranı, utilization (kart bazlı), fullness.",
    },
    {
        "DAtabaseName": "EDWDM",
        "SchemaName": "CMP",
        "ObjectName": "vCardLimitFullness",
        "ColumnName": "CustomerPartyId ",
        "ColumnDescription": "Müşterinin DWH anahtarı.",
        "Synonyms": "müşteri SKEY, party id.",
    },
    {
        "DAtabaseName": "EDWDM",
        "SchemaName": "CON",
        "ObjectName": "vCreditCardLimit",
        "ColumnName": "CardLimitRatio",
        "ColumnDescription": "Kart limitinin referans değere oranı. KVKK kapsamında değildir.",
        "Synonyms": None,
    },
    # Exact duplicate key -> dropped with a warning.
    {
        "DAtabaseName": "EDWDM",
        "SchemaName": "CMP",
        "ObjectName": "vCardLimitFullness",
        "ColumnName": "CardLimitFullnessToday",
        "ColumnDescription": "Tekrar.",
        "Synonyms": None,
    },
]
SAMPLE_OBJECTS = [
    {"ObjectKey": "EDWDM.CMP.vCardLimitFullness", "DatasetGroup": "Kart"},
    {"ObjectKey": "EDWDM.CON.vCreditCardLimit", "DatasetGroup": "Kart"},
]


def write_xlsx(path: Path, sheets: Mapping[str, Sequence[Mapping[str, object]]]) -> Path:
    """A workbook with one sheet per entry: a header row, then the records."""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        header = list(dict.fromkeys(k for r in rows for k in r))
        ws.append(header)
        for r in rows:
            ws.append([r.get(h) for h in header])
    wb.save(path)
    return path


@pytest.fixture
def sample_dictionary_path(tmp_path: Path) -> Path:
    return write_xlsx(
        tmp_path / "dictionary.xlsx", {"Objeler": SAMPLE_OBJECTS, "Kolonlar": SAMPLE_ROWS}
    )


@pytest.fixture
def real_dictionary_path() -> Path:
    if not REAL_DICTIONARY.exists():
        pytest.skip("Gerçek sözlük yok (data/ gitignore'da)")
    return REAL_DICTIONARY
