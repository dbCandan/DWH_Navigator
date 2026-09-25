"""Data dictionary, term dictionary and stopword loading (HANDOVER §3).

This is one of the few modules allowed to do I/O. Parsing helpers are pure and
tested on their own.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import re
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from vsa.models import DictColumn, Dictionary, Flag, FlagKind, TermGroup
from vsa.text.normalize import fold, load_stopwords

log = logging.getLogger(__name__)

# Accepts "Eş anlamlılar/aranabilir terimler:", "Eş anlamlılar:", "aranabilir terimler:".
_SYNONYM_MARKER = re.compile(
    r"(?:eş\s+anlamlılar\s*/\s*aranabilir\s+terimler|eş\s+anlamlılar|aranabilir\s+terimler)\s*:",
    re.IGNORECASE,
)
_LEADING_FLAG = re.compile(r"^\s*\[([^\]]*)\]\s*")
_PII_MARKER = re.compile(r"kvkk|kişisel\s+veri", re.IGNORECASE)

# Column-name aliases: the source file spells the first one "DAtabaseName".
_REQUIRED = {
    "database": ("databasename",),
    "schema": ("schemaname",),
    "object": ("objectname",),
    "column": ("columnname",),
    "description": ("columndescription",),
}
_OPTIONAL = {"dataset_group": ("datasetgroup",)}

NAMING_MISMATCH_CATEGORY = "isimlendirme/icerik uyumsuzlugu"


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


def classify_flag(text: str) -> FlagKind:
    head = fold(text)
    if head.startswith("model tahmini"):
        return FlagKind.MODEL_ESTIMATED
    if head.startswith("orijinal aciklama hataliydi"):
        return FlagKind.CORRECTED
    return FlagKind.NEEDS_VERIFICATION


def parse_description(raw: str) -> tuple[str, tuple[str, ...], tuple[Flag, ...]]:
    """Split a raw description into (body, synonyms, leading flags)."""
    text = raw.strip()
    flags: list[Flag] = []
    while m := _LEADING_FLAG.match(text):
        flag_text = m.group(1).strip()
        flags.append(Flag(classify_flag(flag_text), flag_text))
        text = text[m.end() :]

    synonyms: tuple[str, ...] = ()
    marker = _SYNONYM_MARKER.search(text)
    if marker:
        synonyms = tuple(split_synonyms(text[marker.end() :]))
        text = text[: marker.start()]
    return text.strip(), synonyms, tuple(flags)


def _is_account_number_note(column: str, flag: Flag) -> bool:
    """ADR-009: customer number and account number are the same concept, so the
    "different meaning in this object" notes on AccountNumber columns are noise."""
    if flag.kind is not FlagKind.NEEDS_VERIFICATION:
        return False
    if not fold(column).endswith("accountnumber"):
        return False
    text = fold(flag.text)
    return "farkli anlamda" in text or "hesap numarasi" in text


def _resolve_columns(df_columns: Iterable[str]) -> dict[str, str]:
    """Map logical names -> actual DataFrame column names, case-insensitively."""
    lookup = {fold(str(c)).replace(" ", ""): str(c) for c in df_columns}
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
                    f"(mevcut: {', '.join(map(str, df_columns))})"
                )
    return resolved


def _cell(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def build_columns(
    rows: pd.DataFrame, quality: pd.DataFrame | None = None
) -> tuple[list[DictColumn], list[str]]:
    """Turn dictionary rows (+ optional quality findings) into DictColumns. Pure."""
    names = _resolve_columns(rows.columns)
    warnings: list[str] = []

    findings: dict[tuple[str, str], list[Flag]] = {}
    if quality is not None:
        findings = _quality_flags(quality, warnings)

    columns: list[DictColumn] = []
    seen: set[str] = set()
    for i, rec in enumerate(rows.to_dict("records")):
        db, schema = _cell(rec[names["database"]]), _cell(rec[names["schema"]])
        obj, col = _cell(rec[names["object"]]), _cell(rec[names["column"]])
        raw = _cell(rec[names["description"]])
        if not (db and schema and obj and col):
            warnings.append(f"Satır {i + 2}: eksik veritabanı/şema/obje/kolon, atlandı")
            continue
        key = f"{db}.{schema}.{obj}.{col}"
        if key in seen:
            warnings.append(f"Tekrarlanan kolon, ilk kayıt tutuldu: {key}")
            continue
        seen.add(key)

        body, synonyms, flags = parse_description(raw)
        flags = tuple(f for f in flags if not _is_account_number_note(col, f))
        extra = findings.get((fold(obj), fold(col)), [])
        group = _cell(rec[names["dataset_group"]]) if "dataset_group" in names else ""
        columns.append(
            DictColumn(
                id=len(columns),
                database=db,
                schema=schema,
                object_name=obj,
                column=col,
                description=body,
                raw_description=raw,
                synonyms=synonyms,
                flags=flags + tuple(extra),
                dataset_group=group or None,
                has_pii=bool(_PII_MARKER.search(raw)),
            )
        )
    return columns, warnings


def _quality_flags(quality: pd.DataFrame, warnings: list[str]) -> dict[tuple[str, str], list[Flag]]:
    """Sheet2 findings keyed by folded (object, column). Sheet2 has no db/schema."""
    cols = {fold(str(c)): str(c) for c in quality.columns}
    needed = ("kategori", "objectname", "columnname")
    if not all(n in cols for n in needed):
        warnings.append("Kalite sayfası beklenen formatta değil, yok sayıldı")
        return {}
    finding_col = cols.get("bulgu")
    out: dict[tuple[str, str], list[Flag]] = {}
    for rec in quality.to_dict("records"):
        category = _cell(rec[cols["kategori"]])
        obj, col = _cell(rec[cols["objectname"]]), _cell(rec[cols["columnname"]])
        if not (obj and col and category):
            continue
        kind = (
            FlagKind.NAMING_MISMATCH
            if fold(category) == NAMING_MISMATCH_CATEGORY
            else FlagKind.QUALITY_NOTE
        )
        detail = _cell(rec[finding_col]) if finding_col else ""
        text = f"{category}: {detail}" if detail else category
        flags = out.setdefault((fold(obj), fold(col)), [])
        if all(f.kind is not kind or f.text != text for f in flags):
            flags.append(Flag(kind, text))
    return out


# --------------------------------------------------------------------------- I/O


def file_version(path: Path, row_count: int) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return f"{digest}-{row_count}"


def load_dictionary(
    path: Path, sheet: str = "Sheet1", quality_sheet: str | None = "Sheet2"
) -> Dictionary:
    """Read the dictionary workbook. A missing quality sheet only yields a warning."""
    with pd.ExcelFile(path) as book:
        rows = book.parse(sheet, dtype=str)
        quality: pd.DataFrame | None = None
        extra_warnings: list[str] = []
        if quality_sheet:
            if quality_sheet in book.sheet_names:
                quality = book.parse(quality_sheet, dtype=str)
            else:
                extra_warnings.append(
                    f"Kalite sayfası '{quality_sheet}' bulunamadı; bayraksız devam ediliyor"
                )

    columns, warnings = build_columns(rows, quality)
    warnings = extra_warnings + warnings
    for w in warnings:
        log.info(w)
    if warnings:
        log.warning("Sözlük yüklenirken %d uyarı oluştu (ayrıntı: --verbose)", len(warnings))
    return Dictionary(
        columns=columns,
        source_path=str(path),
        version=file_version(path, len(rows)),
        warnings=warnings,
    )


def load_term_dictionary(path: Path) -> list[TermGroup]:
    """Read ``term,equivalents,domain,note``; missing trailing fields are tolerated."""
    groups: list[TermGroup] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for rec in csv.DictReader(fh):
            term = (rec.get("term") or "").strip()
            if not term:
                continue
            equivalents = tuple(
                e.strip() for e in (rec.get("equivalents") or "").split("|") if e.strip()
            )
            groups.append(
                TermGroup(
                    term=term,
                    equivalents=equivalents,
                    domain=(rec.get("domain") or "").strip(),
                    note=(rec.get("note") or "").strip(),
                )
            )
    return groups


def load_stopword_file(path: Path) -> frozenset[str]:
    if not path.exists():
        log.warning("Durak kelime dosyası bulunamadı: %s", path)
        return frozenset()
    return load_stopwords(path.read_text(encoding="utf-8").splitlines())
