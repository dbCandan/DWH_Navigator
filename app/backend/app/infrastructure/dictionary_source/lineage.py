"""How a column is produced, read from view and procedure code (011-dictionary-sync).

A practical reader, not a SQL parser: it follows a column from its view through common table
expressions, temporary tables and ``INSERT ... SELECT`` statements, down the warehouse layers
(EDW merge, EDWLRY load, EDWSTG source). Each column gets only its own expressions and the filters
that shape them. Only definitions are read, never business rows.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache

MAX_DEPTH = 8
MAX_EVIDENCE_CHARS = 1800
KIND_PLAIN = "duz"  # a plain copy through every layer
KIND_LOGIC = "mantik"  # a condition, calculation, constant or filter shapes the value
KIND_UNKNOWN = "bilinmiyor"

_KEYWORDS = (
    "from",
    "where",
    "group",
    "having",
    "order",
    "union",
    "except",
    "intersect",
)
_CODE_COMMENT = re.compile(
    r"\b(select|from|where|join|case|when|then|end|insert|update|delete|drop|into|cast)\b",
    re.IGNORECASE,
)
_AUTHOR = re.compile(
    r"(created|updated|modified|changed)\s+by|author|developer|geliştiren|\b\d{1,2}[./]\d{1,2}[./]\d{4}\b",
    re.IGNORECASE,
)
_VALIDITY = re.compile(
    r"\s*(?:AND\s+)?GETDATE\(\)\s+BETWEEN\s+[\w.\[\]]+\s+AND\s+[\w.\[\]]+",
    re.IGNORECASE,
)
_TECHNICAL = re.compile(
    r"\s*AND\s+[\w.\[\]]*Edw(?:SourceSystemId|SourceSchemaName|SourceTable|Status)\w*\s*=\s*(?:'[^']*'|\d+)",
    re.IGNORECASE,
)
_FALLBACK = re.compile(
    r"CASE\s+WHEN\s+[\w.]+\s+IS\s+NULL\s+THEN\s+CASE\s+WHEN\s+[\w.\[\]]+\s+IS\s+NULL\s+THEN\s*-99\s+"
    r"ELSE\s*-98\s+END\s+ELSE\s+([\w.]+)\s+END",
    re.IGNORECASE,
)
_HINT = re.compile(r"\s*WITH\s*\(\s*\w+\s*\)|\(\s*NOLOCK\s*\)", re.IGNORECASE)
_REFERENCE = re.compile(r"^\[?(\w+)\]?\.\[?(\w+)\]?$|^\[?(\w+)\]?$")
_TABLE = r"(?:\[?\w+\]?\.){0,3}\[?[#\w]+\]?"
_INSERT = re.compile(
    rf"INSERT\s+(?:INTO\s+)?({_TABLE})[^()]*?\(([^()]*)\)\s*(?=SELECT\b)", re.IGNORECASE
)
_SELECT_INTO = re.compile(rf"\bINTO\s+({_TABLE})\s+FROM\b", re.IGNORECASE)
_SOURCE = re.compile(
    rf"(?:\bFROM|\bJOIN)\s+({_TABLE})(?:\s+(?:AS\s+)?(?!ON\b|WHERE\b|INNER\b|LEFT\b|RIGHT\b|FULL\b|CROSS\b|JOIN\b|GROUP\b|ORDER\b)(\w+))?",
    re.IGNORECASE,
)
_JOIN = re.compile(
    r"((?:INNER\s+|LEFT\s+(?:OUTER\s+)?|RIGHT\s+(?:OUTER\s+)?|FULL\s+(?:OUTER\s+)?|CROSS\s+)?JOIN\b.*?)"
    r"(?=(?:INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+|CROSS\s+)?JOIN\b|\bWHERE\b|\bGROUP\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def clean_sql(sql: str) -> str:
    """No block comments, commented-out code or author lines; rule comments stay."""

    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    lines = []
    for line in sql.splitlines():
        code, separator, comment = line.partition("--")
        if (
            separator
            and comment.strip()
            and (_CODE_COMMENT.search(comment) or _AUTHOR.search(comment))
        ):
            line = code
        if line.strip():
            lines.append(line.rstrip())
    return _HINT.sub("", "\n".join(lines))


def _flat(sql: str) -> str:
    """One line, comments dropped, for parsing."""

    return " ".join(re.sub(r"--[^\n]*", " ", sql).split())


def _name(table: str) -> str:
    return table.replace("[", "").replace("]", "").casefold()


def _scan(text: str) -> Iterable[tuple[int, str, int]]:
    """(position, character, parenthesis depth) outside strings and brackets."""

    depth = 0
    quoted = False
    bracket = False
    for position, char in enumerate(text):
        if quoted:
            quoted = char != "'"
        elif bracket:
            bracket = char != "]"
        elif char == "'":
            quoted = True
        elif char == "[":
            bracket = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        else:
            yield position, char, depth


def split_top(text: str) -> list[str]:
    """Split on commas outside parentheses, strings and CASE blocks."""

    parts: list[str] = []
    start = 0
    for position, char, depth in _scan(text):
        if char == "," and depth == 0:
            head = text[start:position]
            opened = len(re.findall(r"\bCASE\b", head, re.IGNORECASE))
            closed = len(re.findall(r"\bEND\b", head, re.IGNORECASE))
            if opened <= closed:
                parts.append(head)
                start = position + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def _keyword_at(text: str, position: int) -> str:
    match = re.match(r"[A-Za-z]+", text[position:])
    if match is None or (
        position and (text[position - 1].isalnum() or text[position - 1] in "_#@.")
    ):
        return ""
    return match.group(0).casefold()


def _top_keywords(text: str) -> list[tuple[int, str]]:
    return [
        (position, word)
        for position, char, depth in _scan(text)
        if depth == 0
        and char.isalpha()
        and (word := _keyword_at(text, position)) in _KEYWORDS
    ]


def select_item(text: str) -> tuple[str, str]:
    """(output name, expression) of one select list entry."""

    text = text.strip()
    match = re.match(r"^\[?(\w+)\]?\s*=(?!=)\s*(.+)$", text, re.DOTALL)
    if match and not text.lower().startswith("case"):
        return match.group(1), match.group(2).strip()
    match = re.match(r"^(.*\S)\s+AS\s+\[?(\w+)\]?$", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(2), match.group(1).strip()
    match = re.match(r"^(.*[\s)'])\[?(\w+)\]?$", text, re.DOTALL)
    if match and match.group(2).casefold() != "end" and match.group(1).strip():
        return match.group(2), match.group(1).strip()
    reference = _REFERENCE.match(text)
    if reference:
        return reference.group(2) or reference.group(3), text
    return "", text


@dataclass(slots=True)
class Query:
    items: dict[str, tuple[str, str]] = field(
        default_factory=dict
    )  # folded name -> (name, expr)
    ordered: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(
        default_factory=dict
    )  # folded alias -> folded table
    joins: dict[str, str] = field(default_factory=dict)  # folded alias -> join text
    where: str = ""
    ctes: dict[str, Query] = field(default_factory=dict)
    branches: int = 1


def _closing(text: str, opening: int) -> int:
    depth = 0
    for position in range(opening, len(text)):
        if text[position] == "(":
            depth += 1
        elif text[position] == ")":
            depth -= 1
            if depth == 0:
                return position
    return len(text) - 1


def _split_ctes(text: str) -> tuple[dict[str, str], str]:
    match = re.search(r"\bWITH\s+(\w+)\s*(?:\([^)]*\))?\s+AS\s*\(", text, re.IGNORECASE)
    if match is None or re.search(r"\bSELECT\b", text[: match.start()], re.IGNORECASE):
        return {}, text
    ctes: dict[str, str] = {}
    position = match.start()
    pattern = re.compile(
        r"(?:WITH\s+|,\s*)(\w+)\s*(?:\([^)]*\))?\s+AS\s*\(", re.IGNORECASE
    )
    while True:
        found = pattern.match(text, position)
        if found is None:
            return ctes, text[position:]
        end = _closing(text, found.end() - 1)
        ctes[found.group(1).casefold()] = text[found.end() : end]
        position = end + 1
        while position < len(text) and text[position] == " ":
            position += 1


def parse_query(sql: str) -> Query:
    """The outermost SELECT of a statement, with its sources, joins, filters and CTEs."""

    text = _flat(sql)
    cte_texts, body = _split_ctes(text)
    query = Query(ctes={name: parse_query(value) for name, value in cte_texts.items()})
    start = re.search(
        r"\bSELECT\b(?:\s+DISTINCT\b)?(?:\s+TOP\s+\(?\d+\)?)?", body, re.IGNORECASE
    )
    if start is None:
        return query
    body = body[start.end() :]
    marks = _top_keywords(body)
    query.branches = 1 + sum(
        word in ("union", "except", "intersect") for _, word in marks
    )
    from_at = next((p for p, word in marks if word == "from"), len(body))
    for entry in split_top(body[:from_at]):
        name, expression = select_item(entry)
        if name:
            query.items.setdefault(name.casefold(), (name, expression))
            query.ordered.append(name)
        else:
            query.ordered.append("")
    tail_marks = [p for p, word in marks if p > from_at and word != "from"]
    from_end = min(tail_marks, default=len(body))
    clause = body[from_at:from_end]
    for match in _SOURCE.finditer(clause):
        table = _name(match.group(1))
        alias = (match.group(2) or table.rsplit(".", 1)[-1]).casefold()
        query.sources.setdefault(alias, table)
    for join in _JOIN.findall(clause):
        found = _SOURCE.search(join)
        if found:
            alias = (
                found.group(2) or _name(found.group(1)).rsplit(".", 1)[-1]
            ).casefold()
            query.joins[alias] = join.strip()
    where_at = next((p for p, word in marks if word == "where"), None)
    if where_at is not None:
        ends = [p for p, _word in marks if p > where_at]
        query.where = body[where_at : min(ends, default=len(body))].strip()
    return query


@dataclass(slots=True)
class Write:
    columns: list[str]  # target order; empty when the SELECT's own names apply
    query: Query
    module: str


def writes_of(module: str, sql: str) -> dict[str, list[Write]]:
    """Tables a procedure fills, with the SELECT behind each write."""

    text = _flat(sql)
    found: dict[str, list[Write]] = defaultdict(list)
    for match in _INSERT.finditer(text):
        columns = [c.strip(" []") for c in match.group(2).split(",")]
        found[_name(match.group(1))].append(
            Write(columns, parse_query(_statement(text, match.end())), module)
        )
    for match in _SELECT_INTO.finditer(text):
        begin = text.rfind("SELECT", 0, match.start())
        upper = text.upper()
        begin = upper.rfind("SELECT", 0, match.start())
        depth_start = begin
        window = max(0, match.start() - 20000)
        for candidate in reversed(
            list(re.finditer(r"\bSELECT\b", upper[window : match.start()]))
        ):
            inner = text[window + candidate.start() : match.start()]
            if inner.count("(") == inner.count(")"):
                depth_start = window + candidate.start()
                break
        statement = (
            text[depth_start : match.start()] + " " + _statement(text, match.end() - 4)
        )
        found[_name(match.group(1))].append(Write([], parse_query(statement), module))
    return found


_NEXT = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|DROP|TRUNCATE|MERGE|DECLARE|IF|END;|COMMIT)\b",
    re.IGNORECASE,
)


def _statement(text: str, start: int) -> str:
    """Text from ``start`` to the next statement, keeping parenthesised subqueries whole."""

    depth = 0
    for position in range(start, len(text)):
        char = text[position]
        depth += (char == "(") - (char == ")")
        if depth == 0 and char == ";":
            return text[start:position]
        if (
            depth == 0
            and _NEXT.match(text, position)
            and not text[position - 1].isalnum()
        ):
            return text[start:position]
    return text[start:]


@dataclass(slots=True)
class Code:
    """Every definition of the server, indexed for tracing."""

    objects: dict[str, str]  # folded db.schema.name -> cleaned definition
    writers: dict[str, list[Write]] = field(
        default_factory=dict
    )  # folded table -> writes
    locals: dict[str, dict[str, list[Write]]] = field(
        default_factory=dict
    )  # module -> #temp writes

    @classmethod
    def build(cls, definitions: Mapping[str, str]) -> Code:
        code = cls(
            {key.casefold(): clean_sql(value) for key, value in definitions.items()}
        )
        writers: dict[str, list[Write]] = defaultdict(list)
        for key, body in code.objects.items():
            if not re.search(r"\b(?:INSERT|INTO)\b", body, re.IGNORECASE):
                continue
            database = key.split(".", 1)[0]
            local: dict[str, list[Write]] = {}
            for table, writes in writes_of(key, body).items():
                if table.startswith("#"):
                    local[table] = writes
                else:
                    parts = table.split(".")
                    full = table if len(parts) == 3 else f"{database}.{table}"
                    writers[full].extend(writes)
            code.locals[key] = local
        code.writers = dict(writers)
        return code


@dataclass(slots=True)
class Trail:
    steps: list[str] = field(default_factory=list)
    plain: bool = True
    seen: set[tuple[str, str]] = field(default_factory=set)
    visited: list[tuple[str, list[Write]]] = field(default_factory=list)
    quiet: int = 0

    def add(self, text: str) -> None:
        text = " ".join(text.split())
        if self.quiet:
            # Reached through a lookup key: the key's -98/-99 fallback says nothing about the value.
            text = _FALLBACK.sub(r"\1", text)
        if text and text not in self.steps:
            self.steps.append(text)


def _bare(join: str) -> str:
    """A join without validity windows and technical source-system conditions."""

    text = _VALIDITY.sub("", join)
    return _TECHNICAL.sub("", text).strip()


def _narrowing(text: str) -> bool:
    """The condition keeps only some rows, or changes a value's sign or meaning."""

    return (
        re.search(
            r"\bIN\s*\(|=\s*'|[<>]=?\s*[-'\d@]|\*\s*-1|\bLIKE\b", text, re.IGNORECASE
        )
        is not None
    )


def _where(query: Query) -> str:
    where = _VALIDITY.sub("", query.where).strip()
    where = re.sub(r"^WHERE\s+AND\s+", "WHERE ", where, flags=re.IGNORECASE)
    return "" if where.upper() == "WHERE" else where


def _gates(query: Query, references: set[tuple[str, str]]) -> list[str]:
    """Joins whose condition narrows on exactly the columns this expression uses."""

    found = []
    for join in query.joins.values():
        text = _bare(join)
        on = text.split(" ON ", 1)[-1].casefold()
        mentioned = any(f"{alias}.{column}" in on for alias, column in references)
        if mentioned and _narrowing(on):
            found.append(text)
    return found


def _is_plain(expression: str) -> bool:
    """A column reference; a number, NULL or a bare function name is not one."""

    match = _REFERENCE.match(expression.strip())
    if match is None:
        return False
    name = match.group(2) or match.group(3)
    return not name[0].isdigit() and name.casefold() not in ("null", "getdate")


def _references(expression: str) -> set[tuple[str, str]]:
    return {
        (a.casefold(), b.casefold())
        for a, b in re.findall(r"\[?\b([A-Za-z_]\w*)\]?\.\[?(\w+)\]?", expression)
    }


def _item(query: Query, column: str) -> tuple[str, str] | None:
    return query.items.get(column.casefold())


def _trace_query(
    code: Code, module: str, query: Query, column: str, trail: Trail, depth: int
) -> None:
    item = _item(query, column)
    if item is None or depth > MAX_DEPTH:
        return
    name, expression = item
    plain = _is_plain(expression)
    matched = _REFERENCE.match(expression) if plain else None
    rename = matched is not None and (
        (matched.group(2 if "." in expression else 3) or "").casefold()
        != name.casefold()
    )
    if not plain:
        trail.plain = False
        trail.add(f"{expression} AS {name}")
    elif rename:
        trail.add(f"{expression} AS {name}")
    reference = _REFERENCE.match(expression.strip()) if plain else None
    targets: set[tuple[str, str]] = set()
    if reference:
        alias = (reference.group(1) or "").casefold()
        targets.add((alias, (reference.group(2) or reference.group(3)).casefold()))
    else:
        targets |= _references(expression)
        if not targets:
            words = {w.casefold() for w in re.findall(r"\b[A-Za-z_]\w*\b", expression)}
            targets |= {
                ("", w) for cte in query.ctes.values() for w in words if w in cte.items
            }
    for gate in _gates(query, {t for t in targets if t[0]}):
        trail.plain = False
        trail.add(gate)
    if not plain and depth > 0:
        # A calculation inside a CTE or load statement: its filters are part of the value. The
        # view's own WHERE belongs to the object, not to each column.
        where = _where(query)
        if where and _has_literal(where):
            trail.add(where)
        if not any(alias for alias, _ in targets):
            # A bare column of a CTE: every narrowing join shapes the rows it sums.
            for join in query.joins.values():
                text = _bare(join)
                if _narrowing(text.split(" ON ", 1)[-1]):
                    trail.add(text)
    for alias, source_column in sorted(targets):
        table = query.sources.get(alias, "")
        if not alias and len(query.sources) == 1:
            table = next(iter(query.sources.values()))
        if alias and alias in query.joins and not plain:
            trail.add(_bare(query.joins[alias]))
        if alias in query.joins:
            # A value from a lookup depends on the key that reaches it: follow the other side.
            for other, key in _references(query.joins[alias].split(" ON ", 1)[-1]):
                source = query.sources.get(other, "")
                if other != alias and source and not source.startswith("edwutil."):
                    trail.quiet += 1
                    _trace_table(code, module, source, key, trail, depth + 1)
                    trail.quiet -= 1
        cte = query.ctes.get(table.rsplit(".", 1)[-1])
        if cte is None and not alias:
            cte = next(
                (c for c in query.ctes.values() if source_column in c.items), None
            )
        if cte is not None:
            _trace_query(code, module, cte, source_column, trail, depth + 1)
        elif table:
            _trace_table(code, module, table, source_column, trail, depth + 1)
        elif not alias:
            # An unqualified column in a query with joins: the table that writes it is the source.
            for source in query.sources.values():
                if not source.startswith("edwutil."):
                    _trace_table(code, module, source, source_column, trail, depth + 1)


def _has_literal(text: str) -> bool:
    return (
        re.search(
            r"\bIN\s*\(|=\s*'|'\s*\)|[<>]=?\s*['\d@]|DATEADD", text, re.IGNORECASE
        )
        is not None
    )


def _full_name(module: str, table: str) -> str:
    return table if table.count(".") >= 2 else f"{module.split('.', 1)[0]}.{table}"


def _trace_table(
    code: Code, module: str, table: str, column: str, trail: Trail, depth: int
) -> None:
    if depth > MAX_DEPTH or (table, column) in trail.seen:
        return
    trail.seen.add((table, column))
    if table.startswith("#"):
        writes = code.locals.get(module, {}).get(table, [])
        owner = module
    else:
        full = _full_name(module, table)
        writes = code.writers.get(full, [])
        trail.visited.append((full, writes))
        owner = ""
        parts = full.split(".")
        if parts[0] == "edw" and len(parts) == 3:
            # The EDW merge procedures copy the same-named EDWLRY table, adding history only.
            layer = f"edwlry.{parts[1]}.{parts[2]}"
            if layer in code.writers:
                _trace_table(code, module, layer, column, trail, depth + 1)
                return
        if full.startswith("edwstg."):
            trail.add(f"Kaynak: {full}.{column}")
            return
        view = code.objects.get(full)
        if (
            view is not None
            and not writes
            and re.search(r"\bCREATE\s+VIEW\b", view, re.IGNORECASE)
        ):
            # A view reading another view: the calculation lives one level down.
            _trace_query(code, full, view_query(view), column, trail, depth + 1)
            return
    for write in writes[:4]:
        place = owner or write.module
        if write.columns:
            lowered = [c.casefold() for c in write.columns]
            if column.casefold() not in lowered:
                continue
            index = lowered.index(column.casefold())
            if index < len(write.query.ordered) and write.query.ordered[index]:
                mapped = write.query.ordered[index]
            else:
                mapped = column
        else:
            mapped = column
        _trace_query(code, place, write.query, mapped, trail, depth + 1)


@dataclass(frozen=True, slots=True)
class ColumnEvidence:
    kind: str
    steps: tuple[str, ...]


def _constants(code: Code, column: str, modules: Iterable[str]) -> list[str]:
    """Literal values a procedure gives this column in its temporary sets, with their rule notes."""

    found: list[str] = []
    for module in sorted(modules):
        body = code.objects.get(module, "")
        for table, writes in code.locals.get(module, {}).items():
            for write in writes:
                item = _item(write.query, column)
                if item is None or not re.fullmatch(r"-?\d+|'[^']*'", item[1].strip()):
                    continue
                note = _note(body, table)
                found.append(f"{item[1].strip()}: {table.lstrip('#')}{note}")
    return found[:14]


def _updates(code: Code, column: str, modules: Iterable[str]) -> list[str]:
    """Values a load procedure sets afterwards with UPDATE, when no insert carries the column."""

    target = re.compile(
        rf"(?:\bSET\b|,)\s*(?:\w+\.)?\[?{re.escape(column)}\]?\s*=\s*"
        r"(CASE\b.*?\bEND\b|[^,;]+?)(?=\s*(?:,|\bFROM\b|\bWHERE\b|;|$))",
        re.IGNORECASE | re.DOTALL,
    )
    found: list[str] = []
    for module in sorted(modules):
        for statement in _update_statements(code.objects.get(module, "")):
            match = target.search(statement)
            if match:
                found.append(
                    f"Sonradan güncellenir: {' '.join(statement.split())[:400]}"
                )
    return found[:3]


@lru_cache(maxsize=1024)
def _update_statements(body: str) -> tuple[str, ...]:
    """A module's UPDATE statements, split once per definition (the trace asks per column)."""

    return tuple(
        re.findall(
            r"\bUPDATE\b.*?(?=\bUPDATE\b|\bINSERT\b|;|\Z)",
            _flat(body),
            re.IGNORECASE | re.DOTALL,
        )
    )


def _note(body: str, table: str) -> str:
    """The comment lines written just before a temporary set."""

    lines = body.splitlines()
    wanted = re.compile(rf"\bINTO\s+{re.escape(table)}\b", re.IGNORECASE)
    for index, line in enumerate(lines):
        if wanted.search(line):
            notes = [
                part.split("--", 1)[1].strip()
                for part in lines[max(0, index - 12) : index]
                if "--" in part and part.split("--", 1)[1].strip()
            ]
            return f" ({' '.join(notes[-2:])[:160]})" if notes else ""
    return ""


def column_evidence(code: Code, view_key: str, column: str) -> ColumnEvidence:
    body = code.objects.get(view_key.casefold())
    if body is None:
        return ColumnEvidence(KIND_UNKNOWN, ())
    query: Query | None = _view_query(body)
    if query is not None and column.casefold() not in query.items:
        query = _result_query(body, column)
    if query is None:
        return _snippet(body, column)
    trail = Trail()
    _trace_query(code, view_key.casefold(), query, column, trail, 0)
    # The load modules of the warehouse tables the trail went through, each writers list once:
    # the same set as checking every writers list of the server against the trail.
    modules = {
        w.module
        for table, writes in {id(w): (t, w) for t, w in trail.visited}.values()
        if table.startswith("edw")
        for w in writes
    }
    constants = _constants(code, column, modules)
    if constants:
        trail.plain = False
        trail.steps.extend(constants)
    if not trail.steps:
        updates = _updates(code, column, modules)
        if updates:
            trail.plain = False
            trail.steps.extend(updates)
    steps: list[str] = []
    size = 0
    for step in trail.steps:
        if size + len(step) > MAX_EVIDENCE_CHARS:
            break
        steps.append(step)
        size += len(step)
    return ColumnEvidence(KIND_PLAIN if trail.plain else KIND_LOGIC, tuple(steps))




@lru_cache(maxsize=1024)
def _view_query(body: str) -> Query:
    """``view_query`` parsed once per definition: the trace asks for it per column."""

    return view_query(body)


def view_query(body: str) -> Query:
    return parse_query(
        re.sub(r"(?is)^.*?\bAS\b(?=\s+(?:WITH|SELECT|BEGIN)\b)", "", body, count=1)
    )


def object_scope(code: Code, view_key: str) -> tuple[str, ...]:
    """What limits the whole object: its own filters and those of its CTEs."""

    body = code.objects.get(view_key.casefold())
    if body is None:
        return ()
    query = view_query(body)
    found: list[str] = []
    for part in (query, *query.ctes.values()):
        where = _where(part)
        if where:
            found.append(where)
        for join in part.joins.values():
            text = _bare(join)
            if _narrowing(text.split(" ON ", 1)[-1]):
                found.append(text)
    if query.branches > 1:
        found.append(f"{query.branches} kolu olan UNION")
    return tuple(found)[:8]


def _result_query(body: str, column: str) -> Query | None:
    """A procedure's result set: the last SELECT that returns the column instead of writing it."""

    found = None
    for query in _result_queries(body):
        if column.casefold() in query.items:
            found = query
    return found


@lru_cache(maxsize=512)
def _result_queries(body: str) -> tuple[Query, ...]:
    """Every SELECT of a procedure that returns rows instead of writing them, parsed once."""

    if not re.search(
        r"\bCREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\b", body, re.IGNORECASE
    ):
        return ()
    text = _flat(body)
    found: list[Query] = []
    for match in re.finditer(r"\bSELECT\b", text, re.IGNORECASE):
        before = text[max(0, match.start() - 400) : match.start()]
        tail = re.split(r";|\bEND\b|\bBEGIN\b", before, flags=re.IGNORECASE)[-1]
        if re.search(
            r"\b(?:INSERT|UPDATE|MERGE|EXISTS|IN)\b|\(\s*$|=\s*$", tail, re.IGNORECASE
        ):
            continue
        statement = _statement(text, match.start())
        if re.search(
            r"\bINTO\s+[#@\w\[]", statement.split(" FROM ", 1)[0], re.IGNORECASE
        ):
            continue
        found.append(parse_query(statement))
    return tuple(found)


def _snippet(body: str, column: str) -> ColumnEvidence:
    """A procedure whose result could not be isolated: only the lines naming the column."""

    wanted = re.compile(rf"\b{re.escape(column)}\b", re.IGNORECASE)
    lines = [
        " ".join(line.split()) for line in body.splitlines() if wanted.search(line)
    ]
    return ColumnEvidence(KIND_UNKNOWN, tuple(lines[:6]))
