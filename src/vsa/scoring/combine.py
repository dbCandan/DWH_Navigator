"""Confidence levels."""

from __future__ import annotations

from vsa.models import Level

HIGH_THRESHOLD = 0.80
MEDIUM_THRESHOLD = 0.50


def level_for(score: float) -> Level:
    """Level on the score as shown to people (whole percent): %80 is always "Yüksek",
    never "Orta" because the raw value was 0.797."""
    score = round(score, 2)
    if score >= HIGH_THRESHOLD:
        return Level.HIGH
    if score >= MEDIUM_THRESHOLD:
        return Level.MEDIUM
    return Level.LOW

