"""The vote weighting against the source 76e21a3 (006-answer-feedback Requirement 17,
Acceptance 1).

``assess`` and ``apply`` give the source's views and shaped answers for 400 generated row sets and
answers. The source side is the committed snapshot; ``python -m tests.parity.harness
--verify-snapshot`` rebuilds it from the source copy.
"""

from __future__ import annotations

import json

import pytest

from tests.parity import harness, votes

pytestmark = pytest.mark.unit


def test_the_weighting_is_the_sources() -> None:
    source = json.loads((harness.SNAPSHOT / "votes.json").read_text(encoding="utf-8"))
    target = json.loads(json.dumps(votes.collect("target"), ensure_ascii=False))
    assert source["scenarios"] == target["scenarios"] == votes.SCENARIOS
    differing = [k for k, v in source["results"].items() if target["results"].get(k) != v]
    assert differing == []
