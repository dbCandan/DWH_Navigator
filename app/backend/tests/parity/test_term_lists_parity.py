"""The term list's reading and report against the source 76e21a3 (005-list-search Decision 10,
Acceptance 1 and 2).

``parse_term_sheet`` gives the source's terms, header, notes and messages for every row set; the
whole reading of in-memory workbooks gives the source's result or message; the list report of
running, stopped and complete lists is the source's workbook cell by cell, links included. The
source side is the committed snapshot; ``python -m tests.parity.harness --verify-snapshot``
rebuilds it from the source copy.
"""

from __future__ import annotations

import json

import pytest

from tests.parity import harness, term_lists

pytestmark = pytest.mark.unit


def test_the_reading_and_the_report_are_the_sources() -> None:
    source = json.loads((harness.SNAPSHOT / "term_lists.json").read_text(encoding="utf-8"))
    target = json.loads(json.dumps(term_lists.collect("target"), ensure_ascii=False))
    for kind in ("parse", "read"):
        differing = [i for i, (s, t) in enumerate(zip(source[kind], target[kind])) if s != t]
        assert differing == [] and len(source[kind]) == len(target[kind]), kind
    assert target["reports"] == source["reports"]
    assert len(source["reports"]) == 5
