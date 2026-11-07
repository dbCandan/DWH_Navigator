"""Apply the curation rules to a merge plan; an admin's edit is never touched.

Runs after the model filled and described the plan, before the version is written. Every field it
changes becomes a ``*_normalized`` report line, and what a rule removed stays in the record's
bookkeeping (``kept['removed']``) instead of a field Navigator reads.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.services.dictionary_curation.decisions import Decisions
from app.services.dictionary_curation.object_rules import align_object
from app.services.dictionary_curation.text_rules import (
    clean_description,
    clean_summary,
    clean_synonyms,
    code_literals,
)
from app.services.dictionary_sync_merge import (
    ORIGIN_EDITED,
    Change,
    MergedColumn,
    MergedTable,
    fold,
)

KIND_TABLE = "table_normalized"
KIND_COLUMN = "column_normalized"
Evidence = Mapping[tuple[str, str], Sequence[str]]


@dataclass(slots=True)
class NormalizeOutcome:
    changes: list[Change] = field(default_factory=list)
    tables: int = 0
    columns: int = 0


def object_code(code: Mapping[str, str]) -> dict[str, list[str]]:
    """Each object's definitions: its own body and the load procedure named after it (ins_…)."""

    by_name: dict[str, list[str]] = defaultdict(list)
    for key, body in code.items():
        name = fold(key.rsplit(".", 1)[-1])
        by_name[name].append(body)
    found: dict[str, list[str]] = {}
    for key in code:
        name = fold(key.rsplit(".", 1)[-1])
        stem = name[1:] if name.startswith("v") else name
        found[fold(key)] = [*by_name.get(name, []), *by_name.get(f"ins_{stem}", [])]
    return found


def _set(
    outcome: NormalizeOutcome,
    kind: str,
    table: MergedTable,
    record: dict[str, str],
    origins: dict[str, str],
    name: str,
    value: str,
    column: str = "",
) -> bool:
    old = record.get(name) or ""
    if value == old or origins.get(name) == ORIGIN_EDITED:
        return False
    record[name] = value
    outcome.changes.append(Change(kind, table.key, column, name, old, value, origins.get(name, "")))
    return True


def _keep_removed(kept: dict[str, object], removed: list[str]) -> None:
    if removed:
        earlier = [r for r in kept.get("removed", []) if isinstance(r, str)]  # type: ignore[union-attr]
        kept["removed"] = list(dict.fromkeys([*earlier, *removed]))[:20]


def normalize_column(
    outcome: NormalizeOutcome,
    table: MergedTable,
    row: MergedColumn,
    support: str,
    decisions: Decisions,
) -> bool:
    record = row.record
    changed = False
    if row.origins.get("ColumnDescription") != ORIGIN_EDITED:
        text, removed = clean_description(record.get("ColumnDescription", ""), support)
        if text:
            changed |= _set(outcome, KIND_COLUMN, table, record, row.origins, "ColumnDescription", text, record["ColumnName"])
        _keep_removed(row.kept, removed)
    synonyms = clean_synonyms(record.get("Synonyms", ""), record.get("ColumnDescription", ""))
    if synonyms:
        changed |= _set(outcome, KIND_COLUMN, table, record, row.origins, "Synonyms", synonyms, record["ColumnName"])
    summary = clean_summary(record.get("Summary", ""), support, decisions.summary_max_chars)
    if summary:
        changed |= _set(outcome, KIND_COLUMN, table, record, row.origins, "Summary", summary, record["ColumnName"])
    return changed


def normalize_tables(
    tables: Sequence[MergedTable],
    code: Mapping[str, str],
    decisions: Decisions,
    evidence: Evidence | None = None,
) -> NormalizeOutcome:
    """Clean every table of the plan in place and report each changed field."""

    outcome = NormalizeOutcome()
    bodies = object_code(code)
    known = evidence or {}
    for table in tables:
        literals = code_literals(bodies.get(fold(table.key), []))
        changed = False
        if table.origins.get("ObjectDescription") != ORIGIN_EDITED:
            text, removed = clean_description(table.record.get("ObjectDescription", ""), literals)
            if text:
                changed |= _set(outcome, KIND_TABLE, table, table.record, table.origins, "ObjectDescription", text)
            _keep_removed(table.kept, removed)
        names = [c.record["ColumnName"] for c in table.columns]
        for name, value in align_object(table.record, names, decisions).items():
            changed |= _set(outcome, KIND_TABLE, table, table.record, table.origins, name, value)
        outcome.tables += changed
        for row in table.columns:
            trail = " ".join(known.get((fold(table.key), fold(row.record["ColumnName"])), ()))
            support = " ".join((trail, row.record.get("ColumnDescription", ""), literals))
            outcome.columns += normalize_column(outcome, table, row, support, decisions)
    return outcome
