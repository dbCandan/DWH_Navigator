"""The dictionary template: workbook -> records -> Dictionary (dictionary-management).

Records keep the template's own column names and cell texts, so the stored dictionary is
parsed by the very code that parses the workbook (``loader.build_columns`` /
``object_profiles``) and an export gives the template back. The validation order, the
messages, the content digest and the version are the source's. Pure: the workbook comes as
bytes and the records go to and come from PostgreSQL through the caller.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.analysis import Dictionary
from app.services.analysis.loader import (
    OBJECTS_SHEET,
    TooManyRows,
    _cell,
    _resolve_columns,
    build_columns,
    file_version,
    object_profiles,
    read_workbook,
    records,
)

COLUMNS_SHEET = "Kolonlar"
OBJECT_FIELDS = (
    "ObjectKey", "DatabaseName", "SchemaName", "ObjectName", "ObjectDescription", "Grain",
    "KeyColumns", "TimeColumns", "BusinessDomain", "DatasetGroup",
)  # fmt: skip
COLUMN_FIELDS = (
    "DatabaseName", "SchemaName", "ObjectName", "ColumnName", "ColumnDescription", "Synonyms",
    "Role", "Summary",
)  # fmt: skip
# Logical column (loader) -> its name in the template; other spellings are renamed on import.
TEMPLATE_NAME = {
    "database": "DatabaseName", "schema": "SchemaName", "object": "ObjectName",
    "column": "ColumnName", "description": "ColumnDescription", "synonyms": "Synonyms",
    "role": "Role", "summary": "Summary",
}  # fmt: skip
MAX_IMPORT_ROWS = 200_000  # the dictionary has ~11k columns; a bigger file is not one
# The name answers and reports give as the dictionary's source (Decision 11).
SOURCE_NAME = "dictionary.jsonl"


@dataclass(slots=True)
class WorkbookImport:
    """A checked workbook: its records in the stored shape, version, digest and counts."""

    version: str
    digest: str
    objects: list[dict[str, str]]
    columns: list[dict[str, str]]
    object_count: int
    column_count: int
    warnings: list[str] = field(default_factory=list)


def _digest(objects: Sequence[Mapping[str, str]], columns: Sequence[Mapping[str, str]]) -> str:
    blob = json.dumps([objects, columns], ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def _texts(rows: Iterable[Mapping[str, object]], fields: Sequence[str]) -> list[dict[str, str]]:
    """Cell texts as the workbook reader sees them, in one fixed shape: every template
    field (empty: ""), then any other column of the sheet. The same dictionary therefore
    gives the same records whichever way it came in (an export imported back included)."""
    rows = list(rows)
    extra = list(dict.fromkeys(k for r in rows for k in r if k not in fields))
    return [{k: _cell(r.get(k)) for k in (*fields, *extra)} for r in rows]


# --------------------------------------------------------------------------- import


def from_workbook(data: bytes) -> WorkbookImport:
    """A workbook in the dictionary template -> store records, checked the way the app
    reads a dictionary. Raises ValueError (Turkish) when the file does not fit."""
    try:
        sheets = read_workbook(data, MAX_IMPORT_ROWS + 1)
    except TooManyRows:
        limit = f"{MAX_IMPORT_ROWS:,}".replace(",", ".")
        raise ValueError(f"Dosyada çok fazla satır var (en fazla {limit}).") from None
    except Exception as exc:  # not an Excel file, a damaged one…
        raise ValueError("Dosya Excel (.xlsx) olarak okunamadı.") from exc
    if COLUMNS_SHEET not in sheets:
        found = ", ".join(sheets) or "-"
        raise ValueError(f"“{COLUMNS_SHEET}” sayfası yok (dosyadaki sayfalar: {found}). "
                         "Şablonu indirip ona göre doldurun.")  # fmt: skip
    rows = list(records(sheets[COLUMNS_SHEET]))
    if not rows:
        raise ValueError(f"“{COLUMNS_SHEET}” sayfasında kolon yok.")
    rename = {actual: TEMPLATE_NAME[logical]
              for logical, actual in _resolve_columns(rows[0].keys()).items()}  # fmt: skip
    rows = [{rename.get(k, k): v for k, v in r.items()} for r in rows]
    objects = _texts(records(sheets.get(OBJECTS_SHEET, [])), OBJECT_FIELDS)
    columns = _texts(rows, COLUMN_FIELDS)
    profiles = object_profiles(objects)
    parsed, warnings = build_columns(columns, {k: p.group for k, p in profiles.items() if p.group})
    if not parsed:
        raise ValueError(
            "Geçerli kolon satırı yok (veritabanı, şema, obje ve kolon adı dolu olmalı)."
        )
    if OBJECTS_SHEET not in sheets:
        warnings.insert(0, f"“{OBJECTS_SHEET}” sayfası yok: tablo açıklamaları ve gruplar olmadan "
                           "aktarıldı.")  # fmt: skip
    return WorkbookImport(
        version=file_version(data, len(rows)),
        digest=_digest(objects, columns),
        objects=objects,
        columns=columns,
        object_count=len({c.object_key for c in parsed}),
        column_count=len(parsed),
        warnings=warnings,
    )


# --------------------------------------------------------------------------- read


def load_dictionary(
    objects: Sequence[Mapping[str, str]],
    columns: Sequence[Mapping[str, str]],
    version: str,
    digest: str,
) -> Dictionary:
    """Stored records as a Dictionary. Its version is the imported workbook's while the
    records are as imported; records changed by hand get a version of their own."""
    profiles = object_profiles(objects)
    parsed, warnings = build_columns(columns, {k: p.group for k, p in profiles.items() if p.group})
    current = _digest(objects, columns)
    if not version or digest != current:
        version = f"{current}-{len(columns)}"
    return Dictionary(parsed, SOURCE_NAME, version, warnings, profiles)


def empty_dictionary() -> Dictionary:
    """No dictionary imported yet: the app starts and says so (ADR-050)."""
    return Dictionary([], SOURCE_NAME, "", [], {})
