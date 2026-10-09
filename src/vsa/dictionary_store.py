"""The app's data dictionary (ADR-049, ADR-050): ``data/dictionary.jsonl``.

The only dictionary the app reads. It is written only by an import of a workbook in the
dictionary template and can be exported back to that template; no workbook is ever read
as the dictionary itself.

One JSON object per line::

    {"type": "meta", "format": 1, "version": "…", "source": "VeriSozlugu.xlsx", …}
    {"type": "object", "ObjectKey": "…", "ObjectDescription": "…", …}   # Objeler sheet
    {"type": "column", "DatabaseName": "…", "ColumnName": "…", …}       # Kolonlar sheet

Records keep the template's own column names and cell texts, so the store is parsed by
the very code that parses the workbook (``loader.build_columns`` / ``object_profiles``)
and an export gives the template back. Does file I/O.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from vsa.loader import (
    OBJECTS_SHEET,
    TooManyRows,
    _cell,
    _resolve_columns,
    build_columns,
    file_version,
    formulas_as_text,
    object_profiles,
    read_workbook,
    records,
    write_jsonl,
)
from vsa.models import Dictionary

log = logging.getLogger(__name__)

FORMAT = 1
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


@dataclass(slots=True)
class Store:
    meta: dict[str, Any]
    objects: list[dict[str, str]]
    columns: list[dict[str, str]]
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


def from_workbook(path: Path, name: str = "") -> Store:
    """A workbook in the dictionary template -> store records, checked the way the app
    reads a dictionary. Raises ValueError (Turkish) when the file does not fit."""
    try:
        sheets = read_workbook(path, MAX_IMPORT_ROWS + 1)
    except TooManyRows:
        raise ValueError(f"Dosyada çok fazla satır var (en fazla {MAX_IMPORT_ROWS:,}).") from None
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
    meta = {
        "type": "meta",
        "format": FORMAT,
        "version": file_version(path, len(rows)),
        "digest": _digest(objects, columns),
        "source": name or path.name,
        "imported_at": datetime.now().isoformat(timespec="seconds"),
        "objects": len({c.object_key for c in parsed}),
        "columns": len(parsed),
        "warnings": len(warnings),
    }
    return Store(meta, objects, columns, warnings)


def save(store: Store, path: Path) -> None:
    """Write the store at once (a crash never leaves half a file); the previous file is
    kept as ``<name>.bak``. Records the same as the stored ones (an exported store imported
    back) keep the stored version, so kept answers and the index stay valid."""
    if path.is_file():
        try:
            old = read(path).meta
        except (OSError, ValueError):
            old = {}
        if old.get("digest") == store.meta["digest"] and old.get("version"):
            store.meta["version"] = old["version"]
    write_jsonl(path, [
        store.meta,
        *({"type": "object", **r} for r in store.objects),
        *({"type": "column", **r} for r in store.columns),
    ])  # fmt: skip


# --------------------------------------------------------------------------- read


def read(path: Path) -> Store:
    if not path.is_file():
        raise FileNotFoundError(f"Uygulama sözlüğü yok: {path}. Yönetim → Sözlük'ten içe aktarın.")
    meta: dict[str, Any] = {}
    objects: list[dict[str, str]] = []
    columns: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}: {n}. satır JSON değil") from exc
            kind = rec.pop("type", "")
            if kind == "meta":
                meta = {"type": "meta", **rec}
            elif kind == "object":
                objects.append({k: str(v) for k, v in rec.items()})
            elif kind == "column":
                columns.append({k: str(v) for k, v in rec.items()})
    if meta.get("format") != FORMAT:
        raise ValueError(f"{path.name}: tanınmayan biçim; sözlüğü yeniden içe aktarın.")
    return Store(meta, objects, columns)


def load_dictionary(path: Path) -> Dictionary:
    """The store as a Dictionary. Its version is the imported workbook's while the records
    are as imported; a hand-edited file gets a version of its own."""
    store = read(path)
    profiles = object_profiles(store.objects)
    columns, warnings = build_columns(
        store.columns, {k: p.group for k, p in profiles.items() if p.group}
    )
    digest = _digest(store.objects, store.columns)
    version = str(store.meta.get("version", ""))
    if not version or store.meta.get("digest") != digest:
        version = f"{digest}-{len(store.columns)}"
    for w in warnings:
        log.info(w)
    return Dictionary(columns, str(path), version, warnings, profiles)


def empty(path: Path) -> Dictionary:
    """No dictionary imported yet: the app starts and says so (ADR-050)."""
    log.warning("Sözlük yok (%s): Yönetim → Sözlük'ten şablondaki Excel'i içe aktarın", path)
    return Dictionary([], str(path), "", [], {})


def summary(path: Path) -> dict[str, Any]:
    """What the admin screen shows about the store: its meta and every table."""
    store = read(path)
    profiles = object_profiles(store.objects)
    counts: dict[str, int] = {}
    for c in store.columns:
        key = ".".join(c.get(k, "") for k in ("DatabaseName", "SchemaName", "ObjectName"))
        counts[key] = counts.get(key, 0) + 1
    tables = [
        {
            "key": key,
            "name": key.rsplit(".", 1)[-1],
            "group": profiles[key].group if key in profiles else "",
            "domain": profiles[key].domain if key in profiles else "",
            "description": profiles[key].description if key in profiles else "",
            "grain": profiles[key].grain if key in profiles else "",
            "columns": n,
        }
        for key, n in sorted(counts.items())
    ]
    return {"meta": store.meta, "tables": tables, "size": path.stat().st_size}


def table(path: Path, key: str) -> dict[str, Any]:
    """One table of the store: its object record and its column records, as written."""
    store = read(path)
    cols = [c for c in store.columns
            if ".".join(c.get(k, "") for k in ("DatabaseName", "SchemaName", "ObjectName")) == key]
    if not cols:
        raise KeyError(key)
    obj = next((o for o in store.objects if _object_key(o) == key), {})
    return {"key": key, "object": obj, "columns": cols}


def _object_key(o: Mapping[str, str]) -> str:
    return o.get("ObjectKey") or ".".join(
        o.get(k, "") for k in ("DatabaseName", "SchemaName", "ObjectName")
    )


# --------------------------------------------------------------------------- export


def _sheet(
    wb: Workbook, title: str, fields: Sequence[str], rows: Sequence[Mapping[str, str]]
) -> None:
    ws = wb.create_sheet(title)
    extra = [k for r in rows for k in r if k not in fields]
    header = [*fields, *dict.fromkeys(extra)]  # columns the template does not know stay
    ws.append(header)
    for r in rows:
        ws.append([r.get(h) or None for h in header])
    formulas_as_text(ws)
    ws.freeze_panes = "A2"


def export(store: Store | None, out: Path) -> Path:
    """The store in the dictionary template (Objeler · Kolonlar); ``None``: the empty
    template."""
    wb = Workbook()
    wb.remove(wb.worksheets[0])
    _sheet(wb, OBJECTS_SHEET, OBJECT_FIELDS, store.objects if store else [])
    _sheet(wb, COLUMNS_SHEET, COLUMN_FIELDS, store.columns if store else [])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
