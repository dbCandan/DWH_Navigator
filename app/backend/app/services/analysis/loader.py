"""Parsing the dictionary template (dictionary-management Decision 1).

The parsing helpers are pure and byte-for-byte the source's: header mapping, cell texts,
synonym splitting, the KVKK mark, dataset groups, object profiles, row warnings and the
version. A workbook is read from its bytes in memory with openpyxl (read-only, values only;
openpyxl parses the XML with defusedxml); nothing touches the file system.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from io import BytesIO

from openpyxl import load_workbook

from app.domain.analysis import DictColumn, ObjectProfile
from app.domain.turkish_text import fold

_PII_MARKER = re.compile(r"kvkk|kişisel\s+veri", re.IGNORECASE)

# Template column names, matched case-insensitively.
_REQUIRED = {
    "database": ("databasename",),
    "schema": ("schemaname",),
    "object": ("objectname",),
    "column": ("columnname",),
    "description": ("columndescription",),
}
_OPTIONAL = {
    "synonyms": ("synonyms",),
    "role": ("role",),
    "summary": ("summary",),
}

Row = Mapping[str, object]


# --------------------------------------------------------------------------- parsing


def split_synonyms(text: str) -> list[str]:
    """Comma-split that ignores commas inside parentheses; trims a trailing period."""
    items: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth:
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    items.append("".join(buf))
    cleaned = [s.strip().rstrip(".").strip() for s in items]
    return [s for s in cleaned if s]


def _resolve_columns(headers: Iterable[str]) -> dict[str, str]:
    """Map logical names -> actual header names, case-insensitively."""
    headers = list(headers)
    lookup = {fold(str(c)).replace(" ", ""): str(c) for c in headers}
    resolved: dict[str, str] = {}
    for logical, aliases in {**_REQUIRED, **_OPTIONAL}.items():
        for alias in aliases:
            if alias in lookup:
                resolved[logical] = lookup[alias]
                break
        else:
            if logical in _REQUIRED:
                raise ValueError(
                    f"Sözlükte zorunlu kolon bulunamadı: {aliases[0]} "
                    f"(mevcut: {', '.join(map(str, headers))})"
                )
    return resolved


def _cell(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):  # empty / NaN
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # a number cell reads "5", not "5.0"
    return str(value).strip()


OBJECTS_SHEET = "Objeler"


def _names(cell: object) -> list[str]:
    return [n.strip() for n in _cell(cell).split(",") if n.strip()]


def object_profiles(objects: Iterable[Row]) -> dict[str, ObjectProfile]:
    """The object sheet as profiles keyed by ``DB.Schema.Object``. Pure."""
    out: dict[str, ObjectProfile] = {}
    for rec in objects:
        key = _cell(rec.get("ObjectKey")) or ".".join(
            _cell(rec.get(c)) for c in ("DatabaseName", "SchemaName", "ObjectName")
        )
        if not key.strip("."):
            continue
        out[key] = ObjectProfile(
            key=key,
            description=_cell(rec.get("ObjectDescription")),
            grain=_cell(rec.get("Grain")),
            time_columns=tuple(_names(rec.get("TimeColumns"))),
            domain=_cell(rec.get("BusinessDomain")),
            group=_cell(rec.get("DatasetGroup")),
        )
    return out


def build_columns(
    rows: Sequence[Row], groups: Mapping[str, str] | None = None
) -> tuple[list[DictColumn], list[str]]:
    """Turn dictionary rows into DictColumns. Pure. A column's DatasetGroup comes from
    its object (``groups``, read from the object sheet)."""
    names = _resolve_columns(rows[0].keys() if rows else ())
    groups = groups or {}
    warnings: list[str] = []

    columns: list[DictColumn] = []
    seen: set[str] = set()
    for i, rec in enumerate(rows):
        db, schema = _cell(rec.get(names["database"])), _cell(rec.get(names["schema"]))
        obj, col = _cell(rec.get(names["object"])), _cell(rec.get(names["column"]))
        description = _cell(rec.get(names["description"]))
        if not (db and schema and obj and col):
            warnings.append(f"Satır {i + 2}: eksik veritabanı/şema/obje/kolon, atlandı")
            continue
        key = f"{db}.{schema}.{obj}.{col}"
        if key in seen:
            warnings.append(f"Tekrarlanan kolon, ilk kayıt tutuldu: {key}")
            continue
        seen.add(key)

        listed = _cell(rec.get(names["synonyms"])) if "synonyms" in names else ""
        columns.append(
            DictColumn(
                id=len(columns),
                database=db,
                schema=schema,
                object_name=obj,
                column=col,
                description=description,
                synonyms=tuple(split_synonyms(listed)),
                dataset_group=groups.get(f"{db}.{schema}.{obj}") or None,
                has_pii=bool(_PII_MARKER.search(f"{description} {listed}")),
                role=_cell(rec.get(names["role"])) if "role" in names else "",
                summary=_cell(rec.get(names["summary"])) if "summary" in names else "",
            )
        )
    return columns, warnings


# --------------------------------------------------------------------------- workbook bytes


def file_version(data: bytes, row_count: int) -> str:
    digest = hashlib.sha256(data).hexdigest()[:12]
    return f"{digest}-{row_count}"


class TooManyRows(ValueError):
    pass


def _sheet_rows(
    sheet: Iterable[Sequence[object]], max_rows: int | None = None
) -> list[list[object]]:
    """Every row of a sheet as a list; trailing empty rows dropped. More than ``max_rows``
    rows raises ``TooManyRows`` before the rest is read (a crafted upload cannot make the
    server unpack millions of rows)."""
    rows: list[list[object]] = []
    for r in sheet:
        if max_rows is not None and len(rows) >= max_rows:
            if any(_cell(c) for c in r):
                raise TooManyRows(str(max_rows))
            continue
        rows.append(list(r))
    while rows and not any(_cell(c) for c in rows[-1]):
        rows.pop()
    return rows


def records(rows: Sequence[Sequence[object]]) -> Iterator[dict[str, object]]:
    """A header row and the rows below it, as dicts keyed by the header."""
    if not rows:
        return
    header = [_cell(h) for h in rows[0]]
    for row in rows[1:]:
        yield {h: v for h, v in zip(header, row, strict=False) if h}


def read_workbook(
    data: bytes, max_rows: int | None = None, max_cols: int | None = None
) -> dict[str, list[list[object]]]:
    """Every sheet of a workbook as rows of cell values (at most ``max_cols`` wide)."""
    book = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        return {
            ws.title: _sheet_rows(ws.iter_rows(max_col=max_cols, values_only=True), max_rows)
            for ws in book.worksheets
        }
    finally:
        book.close()
