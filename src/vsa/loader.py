"""Data dictionary, term dictionary and stopword loading (HANDOVER §3).

This is one of the few modules allowed to do I/O. Parsing helpers are pure and
tested on their own.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from vsa.models import DictColumn, Dictionary, Flag, FlagKind, ObjectProfile, TermGroup
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
_OPTIONAL = {
    "dataset_group": ("datasetgroup",),
    "synonyms": ("synonyms", "esanlamlilar"),
    "role": ("role", "rol"),
    "summary": ("summary", "ozet"),
}



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


OBJECTS_SHEET = "Objeler"


def object_profiles(objects: pd.DataFrame) -> dict[str, ObjectProfile]:
    """The object sheet as profiles keyed by ``DB.Schema.Object``. Pure."""
    out: dict[str, ObjectProfile] = {}
    for rec in objects.to_dict("records"):
        key = _cell(rec.get("ObjectKey")) or ".".join(
            _cell(rec.get(c)) for c in ("DatabaseName", "SchemaName", "ObjectName")
        )
        if not key.strip("."):
            continue
        out[key] = ObjectProfile(
            key=key,
            description=_cell(rec.get("ObjectDescription")),
            grain=_cell(rec.get("Grain")),
            key_columns=tuple(_names(rec.get("KeyColumns"))),
            time_columns=tuple(_names(rec.get("TimeColumns"))),
            domain=_cell(rec.get("BusinessDomain")),
            group=_cell(rec.get("DatasetGroup")),
        )
    return out


def object_groups(objects: pd.DataFrame) -> dict[str, str]:
    """DatasetGroup per ``DB.Schema.Object`` from the object sheet. Pure."""
    return {k: p.group for k, p in object_profiles(objects).items() if p.group}


def build_columns(
    rows: pd.DataFrame, groups: Mapping[str, str] | None = None
) -> tuple[list[DictColumn], list[str]]:
    """Turn dictionary rows into DictColumns. Pure. A column's DatasetGroup comes from
    its own row when the column sheet has one, otherwise from its object (``groups``,
    read from the object sheet)."""
    names = _resolve_columns(rows.columns)
    warnings: list[str] = []

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
        listed = _cell(rec[names["synonyms"]]) if "synonyms" in names else ""
        if listed:  # a Synonyms column wins over a trailing "Eş anlamlılar:" part
            synonyms = tuple(split_synonyms(listed))
        flags = tuple(f for f in flags if not _is_account_number_note(col, f))
        group = _cell(rec[names["dataset_group"]]) if "dataset_group" in names else ""
        if not group and groups:
            group = groups.get(f"{db}.{schema}.{obj}", "")
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
                flags=flags,
                dataset_group=group or None,
                has_pii=bool(_PII_MARKER.search(f"{raw} {listed}")),
                role=_cell(rec[names["role"]]) if "role" in names else "",
                summary=_cell(rec[names["summary"]]) if "summary" in names else "",
            )
        )
    return columns, warnings


# --------------------------------------------------------------------------- I/O


def file_version(path: Path, row_count: int) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return f"{digest}-{row_count}"


def load_dictionary(path: Path, sheet: str = "Kolonlar") -> Dictionary:
    """Read the dictionary workbook: the column sheet, plus the object sheet if present."""
    with pd.ExcelFile(path) as book:
        rows = book.parse(sheet, dtype=str)
        profiles = (
            object_profiles(book.parse(OBJECTS_SHEET, dtype=str))
            if OBJECTS_SHEET in book.sheet_names
            else {}
        )
        groups = {k: p.group for k, p in profiles.items() if p.group} or None

    columns, warnings = build_columns(rows, groups)
    for w in warnings:
        log.info(w)
    if warnings:
        log.warning("Sözlük yüklenirken %d uyarı oluştu (ayrıntı: --verbose)", len(warnings))
    return Dictionary(
        columns=columns,
        source_path=str(path),
        version=file_version(path, len(rows)),
        warnings=warnings,
        objects=profiles,
    )


# --------------------------------------------------------------------------- object catalog


def _names(cell: object) -> list[str]:
    return [n.strip() for n in _cell(cell).split(",") if n.strip()]


def build_catalog(objects: pd.DataFrame, columns: pd.DataFrame) -> list[dict[str, object]]:
    """One record per object of the dictionary's object sheet, for the LLM's table pick:
    profile fields plus the object's column names in dictionary order. Pure."""
    by_object: dict[str, list[str]] = {}
    for rec in columns.to_dict("records"):
        key = ".".join(_cell(rec[c]) for c in ("DatabaseName", "SchemaName", "ObjectName"))
        by_object.setdefault(key, []).append(_cell(rec["ColumnName"]))
    out: list[dict[str, object]] = []
    for rec in objects.to_dict("records"):
        key = _cell(rec["ObjectKey"])
        names = by_object.get(key)
        if not names:
            raise ValueError(f"Objeler sayfasındaki obje kolon sayfasında yok: {key}")
        out.append({
            "obj": key,
            "aciklama": _cell(rec.get("ObjectDescription")),
            "satir": _cell(rec.get("Grain")),
            "anahtar": _names(rec.get("KeyColumns")),
            "zaman": _names(rec.get("TimeColumns")),
            "alan": _cell(rec.get("BusinessDomain")),
            "grup": _cell(rec.get("DatasetGroup")),
            "kolon_sayisi": len(names),
            "kolonlar": names,
        })  # fmt: skip
    return out


def write_catalog(dictionary: Path, out: Path, sheet: str = "Kolonlar") -> int:
    """Read the dictionary's object and column sheets, write the catalog as JSON Lines."""
    with pd.ExcelFile(dictionary) as book:
        objects = book.parse(OBJECTS_SHEET, dtype=str)
        columns = book.parse(sheet, dtype=str)
    records = build_catalog(objects, columns)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records)


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


# --------------------------------------------------------------------------- list search input

MAX_TERMS = 200  # one list is one sitting; a longer one is split by the user
MAX_TERM_CHARS = 500  # longer cells are pasted paragraphs, not search terms
_HEADER_WORDS = frozenset({
    "terim", "terimler", "talep", "talepler", "soru", "sorular", "arama", "kavram", "kavramlar",
    "term", "terms", "query", "queries", "request", "requests", "liste", "aranacak",
    "aranacaklar", "ihtiyac", "konu",
})  # fmt: skip
TERM_FORMAT = "A sütununda, ilk satırda bir başlık (ör. “Terim”), altında her satırda bir terim"


@dataclass(slots=True)
class TermList:
    """A term list read by the one rule set (ADR-033): what will be searched, the header
    that was not, and everything the reader should know about what was left out."""

    terms: list[str]
    header: str
    notes: list[str]


def _column_letter(i: int) -> str:
    letters = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        letters = chr(65 + r) + letters
    return letters


def parse_term_sheet(
    rows: Sequence[Sequence[object]], other_sheets: Sequence[str] = ()
) -> TermList:
    """The first sheet of a term list -> the terms, or a ValueError that says how to fix
    the file. The format is fixed so nothing is guessed: one column (A), the first row is
    always the header and is never searched, one term per row below it."""
    cells = [[" ".join(_cell(c).split()) for c in row] for row in rows]
    filled = sorted({j for row in cells for j, c in enumerate(row) if c})
    if not filled:
        raise ValueError(f"Dosya boş. Beklenen biçim: {TERM_FORMAT}.")
    if filled != [0]:
        where = ", ".join(_column_letter(j) for j in filled)
        if 0 not in filled:
            raise ValueError(f"Terimler A sütununda olmalı; dosyada veri {where} sütununda. "
                             f"Beklenen biçim: {TERM_FORMAT}.")  # fmt: skip
        raise ValueError(f"Liste tek sütunlu olmalı; dosyada {where} sütunlarında veri var. "
                         f"Terimleri A sütununa yazıp diğer sütunları silin. Beklenen biçim: "
                         f"{TERM_FORMAT}.")  # fmt: skip
    column = [row[0] if row else "" for row in cells]
    while column and not column[-1]:
        column.pop()
    header = column[0]
    if not header:
        raise ValueError(f"İlk satır başlık olmalı; A1 hücresi boş. Beklenen biçim: {TERM_FORMAT}.")
    terms: list[str] = []
    seen: set[str] = set()
    blanks = repeats = 0
    for n, text in enumerate(column[1:], 2):
        if not text:
            blanks += 1
            continue
        if len(text) > MAX_TERM_CHARS:
            raise ValueError(f"{n}. satır çok uzun ({len(text)} karakter). Her satıra kısa bir "
                             f"terim ya da soru yazın (en fazla {MAX_TERM_CHARS}).")  # fmt: skip
        key = fold(text)
        if key in seen:
            repeats += 1
            continue
        seen.add(key)
        terms.append(text)
    if not terms:
        raise ValueError(f"Başlığın (“{header}”) altında aranacak terim yok. "
                         f"Beklenen biçim: {TERM_FORMAT}.")  # fmt: skip
    if len(terms) > MAX_TERMS:
        raise ValueError(f"Listede {len(terms)} terim var; tek seferde en fazla {MAX_TERMS}. "
                         "Listeyi bölüp ayrı ayrı yükleyin.")  # fmt: skip
    notes: list[str] = []
    if fold(header).strip(" :.") not in _HEADER_WORDS:
        notes.append(f"İlk satır (“{header}”) başlık sayıldı ve aranmadı.")
    if blanks:
        notes.append(f"{blanks} boş satır atlandı.")
    if repeats:
        notes.append(f"{repeats} tekrar eden terim atlandı (ilk geçtiği satır arandı).")
    if other_sheets:
        notes.append(f"Yalnız ilk sayfa okundu; şu sayfalardaki veriler alınmadı: "
                     f"{', '.join(other_sheets)}.")  # fmt: skip
    return TermList(terms, header, notes)


def load_term_list(path: Path) -> TermList:
    """A term list from an Excel file (first sheet; the other sheets are only checked)."""
    try:
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
    except Exception as exc:  # not an Excel file, a damaged one, an old .xls without engine…
        raise ValueError(f"Dosya Excel (.xlsx) olarak okunamadı. Beklenen biçim: "
                         f"{TERM_FORMAT}.") from exc  # fmt: skip
    if not sheets:
        raise ValueError(f"Dosyada sayfa yok. Beklenen biçim: {TERM_FORMAT}.")
    names = list(sheets)
    others = [n for n in names[1:] if sheets[n].notna().to_numpy().any()]
    return parse_term_sheet(sheets[names[0]].values.tolist(), others)
