"""Which rows an update has to look at, and why: nothing that did not change is in scope.

* A new table is looked at whole; a new column on its own.
* A table whose source text or column list changed (``needs_model`` from the merge) is in scope.
* A column whose computation changed is in scope. Tracing every column through the warehouse code
  takes too long to do on each run, so the check has two steps:
  1. each object has a gate digest: its own definition and the definitions of the modules that
     load the tables it reads, whitespace folded. It is cheap, and reformatting changes nothing.
  2. only an object whose gate changed has its columns traced; each column's trail digest (its
     lineage steps and the object's filters) is compared with the stored one. A column without a
     stored trail counts as changed, since its object's code changed.
* The digests are stored apart from the dictionary versions, so a run that writes no version
  still remembers them. An object without a stored gate is the baseline, not a change.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from app.infrastructure.dictionary_source.lineage import (
    Code,
    column_evidence,
    object_scope,
)
from app.services.dictionary_sync_merge import MergedColumn, MergedTable, fold

REASON_NEW_TABLE = "yeni_tablo"
REASON_NEW_COLUMN = "yeni_kolon"
REASON_SOURCE = "kaynak_degisti"
REASON_CODE = "kod_degisti"
GATE = ""  # the column name under which an object's gate digest is stored
RowKey = tuple[str, str]  # (folded table key, folded column name)
_READS = re.compile(
    r"\b(?:FROM|JOIN)\s+((?:\[?[\w#]+\]?\.){0,2}\[?[\w#]+\]?)", re.IGNORECASE
)


@dataclass(slots=True)
class Scope:
    tables: dict[str, str] = field(default_factory=dict)  # folded key -> reason
    columns: dict[RowKey, str] = field(default_factory=dict)  # row -> reason
    # (table, column) -> the column's lineage steps; (table, "") -> the object's filters
    evidence: dict[RowKey, tuple[str, ...]] = field(default_factory=dict)
    digests: dict[RowKey, str] = field(default_factory=dict)  # to store after the run
    baseline: int = 0  # objects that got their first gate digest
    traced: int = 0  # columns traced in this run
    index: Code | None = field(default=None, repr=False)

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

    def ensure_evidence(
        self, tables: Sequence[MergedTable], rows: Collection[RowKey]
    ) -> None:
        """Trace the given rows that have no trail yet (rows the model will describe)."""

        if self.index is None:
            return
        wanted = set(rows)
        for table in tables:
            key = fold(table.key)
            for row in table.columns:
                item = row_key(table, row)
                if item in wanted and item not in self.evidence:
                    self.evidence[item] = _steps(
                        self.index, table.key, row.record["ColumnName"]
                    )
                    self.traced += 1
            if any(k == key for k, _ in wanted) and (key, GATE) not in self.evidence:
                self.evidence[(key, GATE)] = tuple(object_scope(self.index, table.key))


def row_key(table: MergedTable, row: MergedColumn) -> RowKey:
    return fold(table.key), fold(row.record["ColumnName"])


def _hash(value: object) -> str:
    blob = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def digest(steps: Sequence[str], filters: Sequence[str]) -> str:
    return _hash([list(steps), list(filters)])


def _folded(text: str) -> str:
    return " ".join(text.split())


def _steps(index: Code, table_key: str, column: str) -> tuple[str, ...]:
    return tuple(column_evidence(index, table_key, column).steps)


def gate_digest(index: Code, table_key: str) -> str | None:
    """The object's definition and the definitions that load what it reads, whitespace folded."""

    key = table_key.casefold()
    body = index.objects.get(key)
    if body is None:
        return None
    database = key.split(".", 1)[0]
    modules: set[str] = set()
    for name in _READS.findall(body):
        parts = name.replace("[", "").replace("]", "").casefold().split(".")
        full = (
            ".".join(parts)
            if len(parts) == 3
            else f"{database}." + ".".join(parts[-2:])
        )
        modules.update(write.module for write in index.writers.get(full, ()))
    bodies = [_folded(index.objects.get(m, "")) for m in sorted(modules)]
    return _hash([_folded(body), bodies])


def plan_scope(
    tables: Sequence[MergedTable], code: Mapping[str, str], stored: Mapping[RowKey, str]
) -> Scope:
    """Each row's reason to be looked at, and the digests to store for the next run."""

    scope = Scope(index=Code.build(code) if code else None)
    index = scope.index
    for table in tables:
        key = fold(table.key)
        if table.is_new:
            scope.tables[key] = REASON_NEW_TABLE
        elif table.needs_model:
            scope.tables[key] = REASON_SOURCE
        for row in table.columns:
            if table.is_new:
                scope.columns[row_key(table, row)] = REASON_NEW_TABLE
            elif row.is_new:
                scope.columns[row_key(table, row)] = REASON_NEW_COLUMN
        if index is None:
            continue  # no code read: every stored digest stays as it was
        gate = gate_digest(index, table.key)
        if gate is None:
            continue
        scope.digests[(key, GATE)] = gate
        old_gate = stored.get((key, GATE))
        changed = old_gate is not None and old_gate != gate
        if old_gate is None:
            scope.baseline += 1
        traced = changed or any(
            row_key(table, row) in scope.columns for row in table.columns
        )
        filters = tuple(object_scope(index, table.key)) if traced else ()
        if traced:
            scope.evidence[(key, GATE)] = filters
        for row in table.columns:
            item = row_key(table, row)
            if not (changed or item in scope.columns):
                # Unchanged code: the stored trail stays, no tracing.
                if item in stored:
                    scope.digests[item] = stored[item]
                continue
            steps = _steps(index, table.key, row.record["ColumnName"])
            scope.traced += 1
            scope.evidence[item] = steps
            if not steps and not filters:
                continue
            new_digest = digest(steps, filters)
            scope.digests[item] = new_digest
            if changed and item not in scope.columns and stored.get(item) != new_digest:
                scope.columns[item] = REASON_CODE
    return scope
