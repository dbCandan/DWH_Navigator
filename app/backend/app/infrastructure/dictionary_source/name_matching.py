"""Dictionary names against catalog names (011-dictionary-sync, "Yazım düzeltme").

Pure functions: no driver and no I/O. The catalog spelling is always the right one, and a correction
lives only in the snapshot handed to Navigator; the source is never written.
"""

import unicodedata
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence

from app.domain.dictionary_source import SourceColumn, SourceSnapshot, SourceTable

MIN_SINGLE_EDIT_LENGTH = 6
EDGE_PUNCTUATION = ".,;:'\"`"

# Catalog of one database: schema name -> object name -> column names; None for an object whose
# columns the catalog cannot show (a stored procedure).
DatabaseCatalog = Mapping[str, Mapping[str, Collection[str] | None]]
_Spelling = tuple[str, str, str]


def normal_form(name: str) -> str:
    """Drop every space and invisible character, then edge punctuation, and fold case."""
    visible = "".join(
        character
        for character in name
        if not character.isspace() and unicodedata.category(character) != "Cf"
    )
    return visible.strip(EDGE_PUNCTUATION).casefold()


def _is_single_edit(left: str, right: str) -> bool:
    """One insertion, deletion, adjacent letter swap or letter substitution; no digit involved.

    The first character never takes part: a leading ``v`` marks a view, so ``vCard`` and ``Card``
    are two objects, not a misspelling.
    """
    if left == right or abs(len(left) - len(right)) > 1 or left[:1] != right[:1]:
        return False
    if len(left) == len(right):
        changed = [
            index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]
        ]
        if len(changed) == 1:
            return left[changed[0]].isalpha() and right[changed[0]].isalpha()
        if len(changed) != 2 or changed[1] != changed[0] + 1:
            return False
        first, second = changed
        swapped = left[first] == right[second] and left[second] == right[first]
        return swapped and left[first].isalpha() and left[second].isalpha()
    short, long = (left, right) if len(left) < len(right) else (right, left)
    index = next(
        (index for index, pair in enumerate(zip(short, long)) if pair[0] != pair[1]),
        len(short),
    )
    return long[index + 1 :] == short[index:] and not long[index].isnumeric()


def _single_edit_candidates(normal: str, catalog: Mapping[str, list[str]]) -> list[str]:
    if len(normal) < MIN_SINGLE_EDIT_LENGTH:
        return []
    return [
        name
        for catalog_normal, names in catalog.items()
        if len(catalog_normal) >= MIN_SINGLE_EDIT_LENGTH
        and _is_single_edit(normal, catalog_normal)
        for name in names
    ]


def match_names(
    source_names: Iterable[str],
    catalog_names: Iterable[str],
    *,
    single_edit: bool = False,
    exclusive: bool = True,
) -> dict[str, str | None]:
    """Map each source spelling to its catalog name, or to None when it stays uncorrected.

    ``single_edit`` adds the third step, for object and column names only. ``exclusive`` applies to
    names that identify one dictionary row: a catalog name claimed by two different rows, one of
    them possibly through an exact match, goes to neither correction. Spellings that differ only in
    case are one row under the case-insensitive key, not rivals. Database and schema names are
    shared by many rows, so they match with ``exclusive=False``.
    """
    catalog = set(catalog_names)
    by_normal: dict[str, list[str]] = defaultdict(list)
    for name in sorted(catalog):
        normal = normal_form(name)
        if normal:
            by_normal[normal].append(name)

    result: dict[str, str | None] = {}
    claimants: dict[str, set[str]] = defaultdict(set)
    for name in set(source_names):
        if name in catalog:
            result[name] = name
            claimants[name].add(name.strip().casefold())
            continue
        normal = normal_form(name)
        candidates = by_normal.get(normal, []) if normal else []
        if normal and not candidates and single_edit:
            candidates = _single_edit_candidates(normal, by_normal)
        result[name] = candidates[0] if len(candidates) == 1 else None
        if len(candidates) == 1:
            claimants[candidates[0]].add(name.strip().casefold())

    if exclusive:
        for name, candidate in result.items():
            if (
                candidate is not None
                and name != candidate
                and len(claimants[candidate]) > 1
            ):
                result[name] = None
    return result


def table_key(database: str, schema: str, name: str) -> str:
    return f"{database}.{schema}.{name}"


def _fold(*names: str) -> tuple[str, ...]:
    return tuple(name.casefold() for name in names)


def _first_described[Row: (SourceTable, SourceColumn)](rows: Sequence[Row]) -> Row:
    return next((row for row in rows if row.description), rows[0])


def _locate(
    tables: Sequence[SourceTable],
    columns: Sequence[SourceColumn],
    databases: Mapping[str, str],
    catalogs: Mapping[str, DatabaseCatalog],
    aliases: Mapping[str, str],
) -> dict[_Spelling, _Spelling | None]:
    """Resolve each table spelling once, so definition and detail rows reach the same table."""
    spellings = {(row.database, row.schema, row.name) for row in tables}
    spellings |= {(row.database, row.schema, row.table) for row in columns}
    spellings = {spelling for spelling in spellings if spelling[0] in databases}

    schemas: dict[str, set[str]] = defaultdict(set)
    for database, schema, _ in spellings:
        schemas[databases[database]].add(schema)
    schema_names = {
        database: match_names(names, catalogs[database], exclusive=False)
        for database, names in schemas.items()
    }

    objects: dict[tuple[str, str], set[str]] = defaultdict(set)
    for database, schema, name in spellings:
        real_schema = schema_names[databases[database]][schema]
        if real_schema is not None:
            objects[(databases[database], real_schema)].add(name)
    object_names = {
        scope: match_names(names, catalogs[scope[0]][scope[1]], single_edit=True)
        for scope, names in objects.items()
    }

    located: dict[_Spelling, _Spelling | None] = {}
    for database, schema, name in spellings:
        real_database = databases[database]
        real_schema = schema_names[real_database][schema]
        real_name = (
            None
            if real_schema is None
            else object_names[(real_database, real_schema)][name]
        )
        located[(database, schema, name)] = (
            None
            if real_schema is None or real_name is None
            else (real_database, real_schema, real_name)
        )
    for spelling in located:
        database, schema, name = aliases.get(_alias_key(spelling), "..").split(".", 2)
        if name in catalogs.get(database, {}).get(schema, {}):
            located[spelling] = (database, schema, name)
    return _in_other_schemas(located, databases, catalogs)


def _alias_key(spelling: _Spelling) -> str:
    return table_key(*spelling).casefold()


def _in_other_schemas(
    located: dict[_Spelling, _Spelling | None],
    databases: Mapping[str, str],
    catalogs: Mapping[str, DatabaseCatalog],
) -> dict[_Spelling, _Spelling | None]:
    """An object filed under the wrong schema: the same name, in exactly one other schema.

    Only the schema is corrected, never the name, and a catalog object another row already
    resolved to stays with that row.
    """
    taken = {target for target in located.values() if target is not None}
    candidates: dict[_Spelling, list[_Spelling]] = {}
    for spelling, target in located.items():
        if target is None:
            database = databases[spelling[0]]
            wanted = normal_form(spelling[2])
            candidates[spelling] = [
                (database, schema, name)
                for schema, objects in catalogs[database].items()
                for name in objects
                if normal_form(name) == wanted
            ]
    claims = Counter(found[0] for found in candidates.values() if len(found) == 1)
    for spelling, found in candidates.items():
        if len(found) == 1 and claims[found[0]] == 1 and found[0] not in taken:
            located[spelling] = found[0]
    return located


def reconcile(
    tables: Sequence[SourceTable],
    columns: Sequence[SourceColumn],
    databases: Mapping[str, str],
    catalogs: Mapping[str, DatabaseCatalog],
    aliases: Mapping[str, str] | None = None,
) -> SourceSnapshot:
    """Keep what the catalogs confirm, under the catalog spelling, and account for the rest.

    ``databases`` maps source database spellings to reachable catalog names; rows of any other
    database are left out silently, because the caller reports those databases. Among duplicates
    the first row with a description wins, so the row order must be deterministic.
    """
    known = {source.casefold(): target for source, target in (aliases or {}).items()}
    located = _locate(tables, columns, databases, catalogs, known)

    table_rows: dict[_Spelling, list[SourceTable]] = defaultdict(list)
    column_rows: dict[_Spelling, list[SourceColumn]] = defaultdict(list)
    source_keys: dict[_Spelling, dict[tuple[str, ...], str]] = defaultdict(dict)
    unresolved: dict[tuple[str, ...], str] = {}
    unresolved_definitions: list[tuple[str, ...]] = []
    for table in tables:
        spelling = (table.database, table.schema, table.name)
        if spelling not in located:
            continue
        target = located[spelling]
        if target is None:
            unresolved_definitions.append(_fold(*spelling))
        else:
            table_rows[target].append(table)
            source_keys[target].setdefault(_fold(*spelling), table_key(*spelling))
    for column in columns:
        spelling = (column.database, column.schema, column.table)
        if spelling not in located:
            continue
        target = located[spelling]
        if target is None:
            unresolved.setdefault(_fold(*spelling), table_key(*spelling))
        else:
            column_rows[target].append(column)
            source_keys[target].setdefault(_fold(*spelling), table_key(*spelling))

    # A definition without detail rows never enters, whether or not its object exists.
    skipped = sum(1 for key in unresolved_definitions if key not in unresolved)
    kept_tables: list[SourceTable] = []
    kept_columns: list[SourceColumn] = []
    excluded_tables = set(unresolved.values())
    excluded_columns: set[tuple[str, str]] = set()
    corrected_tables: set[tuple[str, str]] = set()
    corrected_columns: set[tuple[str, str, str]] = set()
    unverified_tables: set[str] = set()

    for target in table_rows.keys() | column_rows.keys():
        database, schema, name = target
        described = table_rows.get(target, [])
        details = column_rows.get(target, [])
        if not details:
            skipped += len(described)
            continue
        available = catalogs[database][schema][name]
        column_names: Mapping[str, str | None]
        if available is None:
            unverified_tables.add(table_key(*target))
            spellings: dict[str, str] = {}
            column_names = {
                r.name: spellings.setdefault(r.name.casefold(), r.name) for r in details
            }
        else:
            column_names = match_names(
                (row.name for row in details), available, single_edit=True
            )
        verified: dict[str, list[SourceColumn]] = defaultdict(list)
        missing: dict[str, str] = {}
        for row in details:
            real_column = column_names[row.name]
            if real_column is None:
                missing.setdefault(row.name.casefold(), row.name)
            else:
                verified[real_column].append(row)
        if not verified:
            # The table entry stands for all its columns, as it does for a missing object.
            excluded_tables.update(source_keys[target].values())
            continue

        key = table_key(*target)
        description = _first_described(described).description if described else ""
        skipped += max(len(described) - 1, 0)
        kept_tables.append(SourceTable(database, schema, name, description))
        for real_column, rows in verified.items():
            chosen = _first_described(rows)
            skipped += len(rows) - 1
            kept_columns.append(
                SourceColumn(
                    database,
                    schema,
                    name,
                    real_column,
                    chosen.description,
                    chosen.group,
                )
            )
            corrected_columns.update(
                (key, row.name, real_column) for row in rows if row.name != real_column
            )
        excluded_columns.update((key, column_name) for column_name in missing.values())
        corrected_tables.update(
            (source_key, key)
            for source_key in source_keys[target].values()
            if source_key != key
        )

    return SourceSnapshot(
        tables=tuple(
            sorted(
                kept_tables,
                key=lambda row: (_fold(row.database, row.schema, row.name), row.name),
            )
        ),
        columns=tuple(
            sorted(
                kept_columns,
                key=lambda row: (
                    _fold(row.database, row.schema, row.table, row.name),
                    row.name,
                ),
            )
        ),
        skipped=skipped,
        excluded_tables=tuple(
            sorted(excluded_tables, key=lambda item: (item.casefold(), item))
        ),
        excluded_columns=tuple(
            sorted(excluded_columns, key=lambda item: (_fold(*item), item))
        ),
        corrected_tables=tuple(
            sorted(corrected_tables, key=lambda item: (_fold(*item), item))
        ),
        corrected_columns=tuple(
            sorted(corrected_columns, key=lambda item: (_fold(*item), item))
        ),
        unverified_tables=tuple(
            sorted(unverified_tables, key=lambda item: (item.casefold(), item))
        ),
        catalogs=catalogs,
    )
