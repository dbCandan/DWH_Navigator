"""Which rows an update has to look at, and why: nothing that did not change is in scope.

* A new table is looked at whole; a new column on its own.
* A table whose source text or column list changed (``needs_model`` from the merge) is in scope.
* A column whose computation changed is in scope: each column has a digest of its code trail (the
  lineage steps and the object's filters), stored apart from the dictionary versions so a run
  that writes no version still remembers it. Reformatting code does not change a trail.
* A row without a stored digest is the baseline, not a change.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from app.infrastructure.dictionary_source.lineage import Code, column_evidence, object_scope
from app.services.dictionary_sync_merge import MergedColumn, MergedTable, fold

REASON_NEW_TABLE = "yeni_tablo"
REASON_NEW_COLUMN = "yeni_kolon"
REASON_SOURCE = "kaynak_degisti"
REASON_CODE = "kod_degisti"
RowKey = tuple[str, str]  # (folded table key, folded column name)
Trace = Callable[[str, str], Sequence[str]]


@dataclass(slots=True)
class Scope:
    tables: dict[str, str] = field(default_factory=dict)  # folded key -> reason
    columns: dict[RowKey, str] = field(default_factory=dict)  # row -> reason
    # (table, column) -> the column's lineage steps; (table, "") -> the object's filters
    evidence: dict[RowKey, tuple[str, ...]] = field(default_factory=dict)
    digests: dict[RowKey, str] = field(default_factory=dict)  # to store after the run
    baseline: int = 0  # rows that got their first digest

    def column_reason(self, table: MergedTable, row: MergedColumn) -> str:
        return self.columns.get(row_key(table, row), "")

    def table_reason(self, table: MergedTable) -> str:
        return self.tables.get(fold(table.key), "")

    @property
    def empty(self) -> bool:
        return not self.tables and not self.columns

    def counts(self) -> dict[str, int]:
        reasons = list(self.tables.values()) + list(self.columns.values())
        return {
            "scope_tables": len(self.tables),
            "scope_columns": len(self.columns),
            "scope_code_changed": reasons.count(REASON_CODE),
        }


def row_key(table: MergedTable, row: MergedColumn) -> RowKey:
    return fold(table.key), fold(row.record["ColumnName"])


def digest(steps: Sequence[str], filters: Sequence[str]) -> str:
    blob = json.dumps([list(steps), list(filters)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def tracer(code: Mapping[str, str]) -> tuple[Trace, Callable[[str], Sequence[str]]]:
    index = Code.build(code) if code else None

    def trace(table_key: str, column: str) -> Sequence[str]:
        return column_evidence(index, table_key, column).steps if index else ()

    def filters(table_key: str) -> Sequence[str]:
        return object_scope(index, table_key) if index else ()

    return trace, filters


def plan_scope(
    tables: Sequence[MergedTable], code: Mapping[str, str], stored: Mapping[RowKey, str]
) -> Scope:
    """Each row's reason to be looked at, and the trail digests to store for the next run."""

    scope = Scope()
    trace, filters_of = tracer(code)
    for table in tables:
        key = fold(table.key)
        filters = tuple(filters_of(table.key))
        scope.evidence[(key, "")] = filters
        if table.is_new:
            scope.tables[key] = REASON_NEW_TABLE
        elif table.needs_model:
            scope.tables[key] = REASON_SOURCE
        for row in table.columns:
            item = row_key(table, row)
            if table.is_new:
                scope.columns[item] = REASON_NEW_TABLE
            elif row.is_new:
                scope.columns[item] = REASON_NEW_COLUMN
            steps = tuple(trace(table.key, row.record["ColumnName"]))
            scope.evidence[item] = steps
            if not steps and not filters:
                continue  # no trail read: the stored digest stays as it was
            new_digest = digest(steps, filters)
            scope.digests[item] = new_digest
            old_digest = stored.get(item)
            if item in scope.columns:
                continue
            if old_digest is None:
                scope.baseline += 1
            elif old_digest != new_digest:
                scope.columns[item] = REASON_CODE
    return scope
