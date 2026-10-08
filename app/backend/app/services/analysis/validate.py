"""Validation against the dictionary (ADR-002). Non-negotiable.

Every (object, column) pair in the output is looked up in the dictionary. Anything
not found is dropped and counted — the drop count is the hallucination indicator; the
dropped names never reach a log. Runs with or without the LLM.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from app.domain.analysis import ObjectMatch


def validate(
    objects: Sequence[ObjectMatch], column_keys: Collection[str]
) -> tuple[list[ObjectMatch], int]:
    """Return (objects with only verified columns, number of dropped rows)."""
    dropped = 0
    kept: list[ObjectMatch] = []
    for m in objects:
        valid = []
        for h in m.columns:
            key = f"{m.object_key}.{h.col.column}"
            if key == h.col.key and key in column_keys:
                valid.append(h)
            else:
                dropped += 1
        if valid:
            m.columns = valid
            kept.append(m)
    return kept, dropped
