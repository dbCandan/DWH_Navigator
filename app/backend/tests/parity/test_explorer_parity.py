"""The dictionary explorer against the source 76e21a3 (007-dictionary-explorer Decision 1,
Acceptance 1).

The star map, the table search of 722 queries (parity questions, table names in several spellings,
schema-qualified names, keys, name and column name parts, empty and short texts) and every table's
detail are the source's ``App.galaxy``, ``App.objects`` and ``App.object_detail`` apart from
``elapsed_ms``. The source side is the committed snapshot; ``python -m tests.parity.harness
--verify-snapshot`` rebuilds it from the source copy.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.parity import explorer, harness

pytestmark = pytest.mark.unit


def test_the_explorer_answers_as_the_source() -> None:
    source: dict[str, Any] = json.loads(
        (harness.SNAPSHOT / "explorer.json").read_text(encoding="utf-8")
    )
    target = json.loads(json.dumps(explorer.collect("target"), ensure_ascii=False))
    assert target["galaxy"] == source["galaxy"]
    assert target["unknown_detail"] is None and source["unknown_detail"] is None
    assert target["details"] == source["details"]
    differing = [
        (key, value["query"])
        for key, value in source["searches"].items()
        if target["searches"].get(key) != value
    ]
    assert differing == []
    assert len(source["searches"]) >= 700 and len(source["galaxy"]) >= 60
