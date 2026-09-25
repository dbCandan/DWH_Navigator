"""Final score combination and labels (HANDOVER §9.1, §9.3, ADR-003)."""

from __future__ import annotations

from vsa.models import Level

HIGH_THRESHOLD = 0.80
MEDIUM_THRESHOLD = 0.50


def level_for(score: float) -> Level:
    if score >= HIGH_THRESHOLD:
        return Level.HIGH
    if score >= MEDIUM_THRESHOLD:
        return Level.MEDIUM
    return Level.LOW


def combine(rule_score: float, llm_score: float | None, w_rule: float, w_llm: float) -> float:
    """``w_rule × rule + w_llm × llm``; with no LLM score the rule score stands alone."""
    if llm_score is None:
        return rule_score
    total = w_rule + w_llm
    return (w_rule * rule_score + w_llm * llm_score) / total
