"""Dictionary workbooks for the analysis tests, built in memory."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO

from openpyxl import Workbook

from app.domain.analysis import Dictionary
from app.services.analysis.dictionary_workbook import from_workbook, load_dictionary

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


def xlsx_bytes(sheets: Mapping[str, Sequence[Mapping[str, object]]]) -> bytes:
    """A workbook with one sheet per entry: a header row, then the records."""
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        header = list(dict.fromkeys(k for r in rows for k in r))
        ws.append(header)
        for r in rows:
            ws.append([r.get(h) for h in header])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def import_workbook(data: bytes) -> Dictionary:
    """A workbook in the dictionary template imported and read back as the engine reads it."""
    imported = from_workbook(data)
    return load_dictionary(imported.objects, imported.columns, imported.version, imported.digest)
