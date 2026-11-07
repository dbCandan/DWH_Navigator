"""The dictionary owner's standing decisions, read from one JSON file.

A decision is data, not code: which columns stay out of the dictionary, which business areas mean
the same thing, which words the explanations use. The bundled ``decisions.json`` holds what the
owner decided while the dictionary was cleaned by hand; a deployment can point at its own copy.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BUNDLED = Path(__file__).with_name("decisions.json")


@dataclass(frozen=True, slots=True)
class Decisions:
    ignored_columns: frozenset[str] = frozenset()  # folded names
    excluded_object_prefixes: tuple[str, ...] = ()  # folded, e.g. "prm_"
    excluded_schemas: frozenset[str] = frozenset()  # folded
    same_value_columns: tuple[tuple[str, ...], ...] = ()  # columns that carry one value
    business_domains: tuple[str, ...] = ()  # the shared names
    domain_aliases: Mapping[str, str] = field(default_factory=dict)  # variant -> shared name
    summary_max_chars: int = 70

    def ignores(self, column: str) -> bool:
        return column.strip().casefold() in self.ignored_columns

    def excludes(self, schema: str, name: str) -> bool:
        folded = name.strip().casefold()
        return schema.strip().casefold() in self.excluded_schemas or folded.startswith(
            self.excluded_object_prefixes
        )

    def domain(self, value: str) -> str:
        value = value.strip()
        return self.domain_aliases.get(value, value)


def _fold_all(values: Any) -> frozenset[str]:
    return frozenset(str(v).strip().casefold() for v in values or () if str(v).strip())


def parse(raw: Mapping[str, Any]) -> Decisions:
    return Decisions(
        ignored_columns=_fold_all(raw.get("ignored_columns")),
        excluded_object_prefixes=tuple(sorted(_fold_all(raw.get("excluded_object_prefixes")))),
        excluded_schemas=_fold_all(raw.get("excluded_schemas")),
        same_value_columns=tuple(tuple(group) for group in raw.get("same_value_columns", ())),
        business_domains=tuple(raw.get("business_domains", ())),
        domain_aliases=dict(raw.get("domain_aliases", {})),
        summary_max_chars=int(raw.get("summary_max_chars", 70)),
    )


def load(path: Path | str | None = None) -> Decisions:
    return parse(json.loads(Path(path or BUNDLED).read_text(encoding="utf-8")))
