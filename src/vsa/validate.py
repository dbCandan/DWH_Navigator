"""Validation against the dictionary (ADR-002). Non-negotiable.

Every (object, column) pair in the output is looked up in the dictionary. Anything
not found is dropped and logged at WARNING — the drop count is the hallucination
indicator. Runs with or without the LLM.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Sequence

from vsa.models import ObjectMatch

log = logging.getLogger(__name__)


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
                log.warning("Doğrulama: sözlükte olmayan alan düşürüldü: %s", key)
        if valid:
            m.columns = valid
            kept.append(m)
        else:
            log.warning("Doğrulama: geçerli alanı kalmayan obje düşürüldü: %s", m.object_key)
    return kept, dropped
