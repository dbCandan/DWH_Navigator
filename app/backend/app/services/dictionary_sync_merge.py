"""Merge a verified source snapshot into the active dictionary (011-dictionary-sync).

Pure functions: the dictionary is never rewritten from scratch, a filled value is kept and every
difference becomes a report line. Keys are ``DB.Schema.Object`` and match case-insensitively. A
name the source spelled wrongly reaches this module already corrected; the record that stood under
the wrong spelling carries its values over instead of counting as removed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from app.domain.dictionary_source import SourceColumn, SourceSnapshot
from app.infrastructure.dictionary_source.name_matching import match_names
from app.services.analysis.dictionary_workbook import COLUMN_FIELDS, OBJECT_FIELDS

ORIGIN_SOURCE = "kaynak"
ORIGIN_MODEL = "model"
ORIGIN_PRIOR = "onceki"
ORIGIN_EDITED = "duzenleme"

OBJECT_MODEL_FIELDS = ("Grain", "KeyColumns", "TimeColumns", "BusinessDomain")
COLUMN_MODEL_FIELDS = ("Synonyms", "Role", "Summary")

_REBUILT_META = frozenset({"origins", "source_digest", "model_pending"})

# The personal-data marking was removed from the product; the sentences it left in texts go too.
_MARKING = re.compile(
    r"[;,]?\s*KVKK\s+kapsamında\s+(?:kişisel|hassas)\s+veri(?:dir|\s+niteliğindedir)?"
    r"(?:\s*[;,]\s*sadece\s+yetkili\s+erişimlerde\s+açık\s+gösterilir)?\.?",
    re.IGNORECASE,
)
_MARKING_SUMMARY = re.compile(r"\s*·\s*KVKK\b", re.IGNORECASE)

Record = dict[str, str]


@dataclass(frozen=True, slots=True)
class Change:
    kind: str
    table_key: str
    column_name: str = ""
    field: str = ""
    old_value: str = ""
    new_value: str = ""
    origin: str = ""


@dataclass(slots=True)
class MergedColumn:
    record: Record
    origins: dict[str, str]
    is_new: bool = False
    kept: dict[str, Any] = field(default_factory=dict)  # bookkeeping carried between versions


@dataclass(slots=True)
class MergedTable:
    key: str
    record: Record
    origins: dict[str, str]
    columns: list[MergedColumn]
    source_digest: str
    needs_model: bool
    is_new: bool
    kept: dict[str, Any] = field(default_factory=dict)

    @property
    def object_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            **self.kept,
            "origins": self.origins,
            "source_digest": self.source_digest,
        }
        if self.needs_model:
            meta["model_pending"] = True
        return meta


@dataclass(slots=True)
class MergePlan:
    tables: list[MergedTable]
    changes: list[Change] = field(default_factory=list)
    prior_table_count: int = 0
    prior_column_count: int = 0
    removed_tables: int = 0
    removed_columns: int = 0

    @property
    def has_changes(self) -> bool:
        return any(not c.kind.endswith(("_excluded", "_corrected", "_kept")) for c in self.changes)

    def removal_share(self) -> float:
        """The larger of the removed table and column shares of the active dictionary."""

        tables = self.removed_tables / self.prior_table_count if self.prior_table_count else 0.0
        columns = self.removed_columns / self.prior_column_count if self.prior_column_count else 0.0
        return max(tables, columns)

    def objects(self) -> list[Record]:
        return [t.record for t in self.tables]

    def columns(self) -> list[Record]:
        return [c.record for t in self.tables for c in t.columns]

    def object_meta(self) -> list[dict[str, Any]]:
        return [t.object_meta for t in self.tables]

    def column_meta(self) -> list[dict[str, Any]]:
        return [{**c.kept, "origins": c.origins} for t in self.tables for c in t.columns]


def fold(value: str) -> str:
    return value.strip().casefold()


def table_key(database: str, schema: str, name: str) -> str:
    return f"{database}.{schema}.{name}"


def record_key(record: Mapping[str, str]) -> str:
    return record.get("ObjectKey") or table_key(
        record.get("DatabaseName", ""), record.get("SchemaName", ""), record.get("ObjectName", "")
    )


def source_digest(description: str, group: str, columns: Sequence[SourceColumn]) -> str:
    """What the source says about a table; load dates are not part of it."""

    rows = sorted((c.name.casefold(), c.description) for c in columns)
    blob = json.dumps([description, group, rows], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def table_group(columns: Sequence[SourceColumn]) -> str:
    """The most frequent filled group of the table's column rows; ties go to the first name."""

    counts = Counter(c.group for c in columns if c.group)
    if not counts:
        return ""
    return min(counts.items(), key=lambda item: (-item[1], item[0]))[0]


def pick(prior: str, prior_origin: str, source: str) -> tuple[str, str]:
    """Filled values stay; only a value the source itself gave follows the source."""

    if not prior:
        return (source, ORIGIN_SOURCE) if source else ("", "")
    if prior_origin == ORIGIN_SOURCE and source and source != prior:
        return source, ORIGIN_SOURCE
    return prior, prior_origin or ORIGIN_PRIOR


def without_marking(text: str) -> str:
    """The text without the marking sentence; a text that is nothing else stays as it is."""

    cleaned = _MARKING.sub("", text).strip()
    if not cleaned or cleaned == text.strip():
        return text
    return cleaned if cleaned.endswith((".", "!", "?", ":", ")")) else f"{cleaned}."


def _unmark_column(record: Record) -> None:
    record["ColumnDescription"] = without_marking(record.get("ColumnDescription", ""))
    record["Summary"] = _MARKING_SUMMARY.sub("", record.get("Summary", ""))


def _kept(
    prior: Mapping[str, str], origins: Mapping[str, str], fields: Sequence[str]
) -> dict[str, str]:
    return {f: origins.get(f) or ORIGIN_PRIOR for f in fields if prior.get(f)}


def _carried(meta: Mapping[str, Any]) -> dict[str, Any]:
    """Bookkeeping that outlives a version, such as the text a description replaced."""

    return {k: v for k, v in meta.items() if k not in _REBUILT_META}


def _column_record(
    source: SourceColumn, prior: Mapping[str, str], prior_origins: Mapping[str, str]
) -> MergedColumn:
    description, origin = pick(
        prior.get("ColumnDescription", ""),
        prior_origins.get("ColumnDescription", ""),
        source.description,
    )
    record: Record = {**{f: "" for f in COLUMN_FIELDS}, **prior}
    record.update(
        DatabaseName=source.database,
        SchemaName=source.schema,
        ObjectName=source.table,
        ColumnName=source.name,
        ColumnDescription=description,
    )
    _unmark_column(record)
    origins = _kept(prior, prior_origins, COLUMN_MODEL_FIELDS)
    origins["ColumnName"] = ORIGIN_SOURCE
    if origin:
        origins["ColumnDescription"] = origin
    return MergedColumn(record, origins)


def _field_changes(
    kind: str,
    key: str,
    column: str,
    prior: Mapping[str, str],
    record: Mapping[str, str],
    origins: Mapping[str, str],
    fields: Sequence[str],
) -> list[Change]:
    return [
        Change(
            kind, key, column, f, prior.get(f, ""), record.get(f, ""), origins.get(f, ORIGIN_SOURCE)
        )
        for f in fields
        if prior.get(f, "") != record.get(f, "")
    ]


def _untouched(
    stored: Mapping[str, str],
    meta: Mapping[str, Any],
    columns: Mapping[str, tuple[Mapping[str, str], Mapping[str, Any]]],
    changes: list[Change],
) -> MergedTable:
    """A record of a database left out of the update: the same, without the marking only."""

    key = record_key(stored)
    record: Record = dict(stored)
    record["ObjectDescription"] = without_marking(record.get("ObjectDescription", ""))
    origins = dict(meta.get("origins", {}))
    changes.extend(_field_changes("table_changed", key, "", stored, record, origins, OBJECT_FIELDS))
    merged: list[MergedColumn] = []
    for old, old_meta in columns.values():
        column: Record = dict(old)
        _unmark_column(column)
        column_origins = dict(old_meta.get("origins", {}))
        changes.extend(
            _field_changes(
                "column_changed",
                key,
                old.get("ColumnName", ""),
                old,
                column,
                column_origins,
                COLUMN_FIELDS,
            )
        )
        merged.append(MergedColumn(column, column_origins, kept=_carried(old_meta)))
    return MergedTable(
        key=key,
        record=record,
        origins=origins,
        columns=merged,
        source_digest=str(meta.get("source_digest", "")),
        needs_model=False,
        is_new=False,
        kept=_carried(meta),
    )


def _catalog_index(snapshot: SourceSnapshot) -> dict[str, frozenset[str] | None]:
    """Folded table key -> folded columns; None for a procedure, whose columns are not listed."""

    return {
        fold(table_key(database, schema, name)): (
            None if columns is None else frozenset(fold(c) for c in columns)
        )
        for database, schemas in snapshot.catalogs.items()
        for schema, objects in schemas.items()
        for name, columns in objects.items()
    }


def merge(
    snapshot: SourceSnapshot,
    prior_objects: Sequence[Mapping[str, str]],
    prior_object_meta: Sequence[Mapping[str, Any]],
    prior_columns: Sequence[Mapping[str, str]],
    prior_column_meta: Sequence[Mapping[str, Any]],
    kept_databases: Collection[str] = (),
) -> MergePlan:
    objects_by_key: dict[str, tuple[Mapping[str, str], Mapping[str, Any]]] = {}
    for index, stored in enumerate(prior_objects):
        meta = prior_object_meta[index] if index < len(prior_object_meta) else {}
        objects_by_key.setdefault(fold(record_key(stored)), (stored, meta))

    columns_by_table: dict[str, dict[str, tuple[Mapping[str, str], Mapping[str, Any]]]] = {}
    for index, stored in enumerate(prior_columns):
        name = stored.get("ColumnName", "")
        if not name:
            continue
        meta = prior_column_meta[index] if index < len(prior_column_meta) else {}
        key = fold(
            table_key(
                stored.get("DatabaseName", ""),
                stored.get("SchemaName", ""),
                stored.get("ObjectName", ""),
            )
        )
        columns_by_table.setdefault(key, {}).setdefault(fold(name), (stored, meta))

    source_key_of = {fold(real): fold(wrong) for wrong, real in snapshot.corrected_tables}
    wrong_column_of = {
        (fold(key), fold(real)): fold(wrong) for key, wrong, real in snapshot.corrected_columns
    }

    source_columns: dict[str, list[SourceColumn]] = {}
    for column in snapshot.columns:
        source_columns.setdefault(
            fold(table_key(column.database, column.schema, column.table)), []
        ).append(column)

    plan = MergePlan(
        tables=[],
        prior_table_count=len(objects_by_key),
        prior_column_count=sum(len(c) for c in columns_by_table.values()),
    )
    used_tables: set[str] = set()
    unverified = {fold(key) for key in snapshot.unverified_tables}
    kept = {database.casefold() for database in kept_databases}
    warehouse = _catalog_index(snapshot)
    for table in sorted(
        snapshot.tables, key=lambda t: fold(table_key(t.database, t.schema, t.name))
    ):
        key = table_key(table.database, table.schema, table.name)
        folded = fold(key)
        columns = sorted(source_columns.get(folded, ()), key=lambda c: c.name.casefold())
        if not columns:
            continue
        lookup = folded if folded in objects_by_key else source_key_of.get(folded, folded)
        prior, prior_meta = objects_by_key.get(lookup, ({}, {}))
        prior_cols = columns_by_table.get(folded) or columns_by_table.get(lookup) or {}
        used_tables.update({folded, lookup})
        is_new = not prior

        prior_origins = prior_meta.get("origins", {})
        group = table_group(columns)
        description, description_origin = pick(
            prior.get("ObjectDescription", ""),
            prior_origins.get("ObjectDescription", ""),
            table.description,
        )
        group_value, group_origin = pick(
            prior.get("DatasetGroup", ""), prior_origins.get("DatasetGroup", ""), group
        )
        record: Record = {**{f: "" for f in OBJECT_FIELDS}, **prior}
        record.update(
            ObjectKey=key,
            DatabaseName=table.database,
            SchemaName=table.schema,
            ObjectName=table.name,
            ObjectDescription=without_marking(description),
            DatasetGroup=group_value,
        )
        origins = _kept(prior, prior_origins, OBJECT_MODEL_FIELDS)
        origins["ObjectName"] = ORIGIN_SOURCE
        if description_origin:
            origins["ObjectDescription"] = description_origin
        if group_origin:
            origins["DatasetGroup"] = group_origin

        merged_columns: list[MergedColumn] = []
        used_columns: set[str] = set()
        columns_differ = False
        # A procedure's columns are typed by hand and no catalog confirms them: Navigator's spelling
        # wins over a near miss in the source.
        navigator_names = (
            match_names(
                [c.name for c in columns],
                [hit[0].get("ColumnName", "") for hit in prior_cols.values()],
                single_edit=True,
            )
            if folded in unverified
            else {}
        )
        for original in columns:
            real = navigator_names.get(original.name)
            column = replace(original, name=real) if real else original
            if column.name != original.name:
                plan.changes.append(
                    Change(
                        "column_corrected",
                        key,
                        column.name,
                        "ColumnName",
                        original.name,
                        column.name,
                        ORIGIN_PRIOR,
                    )
                )
            name = fold(column.name)
            wrong = wrong_column_of.get((folded, name))
            hit = prior_cols.get(name) or (prior_cols.get(wrong) if wrong else None)
            used_columns.update(n for n in (name, wrong) if n)
            old, old_meta = hit if hit else ({}, {})
            merged = _column_record(column, old, old_meta.get("origins", {}))
            merged.is_new = not hit
            merged.kept = _carried(old_meta)
            merged_columns.append(merged)
            if not hit:
                columns_differ = True
                if not is_new:
                    plan.changes.append(Change("column_added", key, column.name))
                continue
            changed = _field_changes(
                "column_changed",
                key,
                column.name,
                old,
                merged.record,
                merged.origins,
                COLUMN_FIELDS,
            )
            plan.changes.extend(changed)
        # A record missing from the source goes only when the warehouse lacks it too; a procedure
        # gives no evidence of absence, so its Navigator columns stay.
        for name, (old, old_meta) in prior_cols.items():
            if name in used_columns:
                continue
            if folded in warehouse and (
                warehouse[folded] is None or name in (warehouse[folded] or ())
            ):
                column_record: Record = dict(old)
                column_record.update(
                    DatabaseName=table.database, SchemaName=table.schema, ObjectName=table.name
                )
                _unmark_column(column_record)
                merged_columns.append(
                    MergedColumn(
                        column_record, dict(old_meta.get("origins", {})), kept=_carried(old_meta)
                    )
                )
                plan.changes.append(Change("column_kept", key, old.get("ColumnName", "")))
                plan.changes.extend(
                    _field_changes(
                        "column_changed",
                        key,
                        old.get("ColumnName", ""),
                        old,
                        column_record,
                        {},
                        COLUMN_FIELDS,
                    )
                )
                continue
            columns_differ = True
            plan.removed_columns += 1
            plan.changes.append(Change("column_removed", key, old.get("ColumnName", "")))
        merged_columns.sort(key=lambda c: fold(c.record["ColumnName"]))

        digest = source_digest(table.description, group, columns)
        known_digest = prior_meta.get("source_digest")
        changed_table = columns_differ if known_digest is None else known_digest != digest
        if is_new:
            plan.changes.append(Change("table_added", key))
        else:
            plan.changes.extend(
                _field_changes("table_changed", key, "", prior, record, origins, OBJECT_FIELDS)
            )
        plan.tables.append(
            MergedTable(
                key=key,
                record=record,
                origins=origins,
                columns=merged_columns,
                source_digest=digest,
                needs_model=is_new or changed_table or bool(prior_meta.get("model_pending")),
                is_new=is_new,
                kept=_carried(prior_meta),
            )
        )

    for folded, (stored, stored_meta) in objects_by_key.items():
        if folded in used_tables:
            continue
        if stored.get("DatabaseName", "").casefold() in kept:
            plan.tables.append(
                _untouched(stored, stored_meta, columns_by_table.get(folded, {}), plan.changes)
            )
            continue
        if folded in warehouse:
            # In Navigator and in the warehouse, only the source forgot it.
            available = warehouse[folded]
            all_columns = columns_by_table.get(folded, {})
            confirmed = {
                name: hit
                for name, hit in all_columns.items()
                if available is None or name in available
            }
            for name, hit in all_columns.items():
                if name not in confirmed:
                    plan.removed_columns += 1
                    plan.changes.append(
                        Change("column_removed", record_key(stored), hit[0].get("ColumnName", ""))
                    )
            if confirmed:
                plan.tables.append(_untouched(stored, stored_meta, confirmed, plan.changes))
                plan.changes.append(Change("table_kept", record_key(stored)))
                continue
        plan.removed_tables += 1
        plan.removed_columns += len(columns_by_table.get(folded, {}))
        plan.changes.append(Change("table_removed", record_key(stored)))
    plan.tables.sort(key=lambda t: fold(t.key))
    for key in snapshot.excluded_tables:
        plan.changes.append(Change("table_excluded", key))
    for key, name in snapshot.excluded_columns:
        plan.changes.append(Change("column_excluded", key, name))
    for wrong, real in snapshot.corrected_tables:
        plan.changes.append(
            Change("table_corrected", real, "", "ObjectName", wrong, real, ORIGIN_SOURCE)
        )
    for key, wrong, real in snapshot.corrected_columns:
        plan.changes.append(
            Change("column_corrected", key, real, "ColumnName", wrong, real, ORIGIN_SOURCE)
        )
    return plan
