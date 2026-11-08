"""An object's own fields agree with its columns.

* Key and time columns name columns the object has, in the object's own spelling.
* A grain cut by a date (veri tarihi, periyot, rapor tarihi …) has that date among its keys.
* The business area uses the shared names of the owner's decisions.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.services.dictionary_curation.decisions import Decisions
from app.services.dictionary_curation.text_rules import split_terms

_GRAIN_TIME = (
    (re.compile(r"karşılık tarihi", re.IGNORECASE), ("ProvisionDate",)),
    (
        re.compile(r"veri tarihi|\bgün|günlük|kesit|× tarih\b", re.IGNORECASE),
        ("DataDate", "RecordDate", "ReportDate", "TranDate"),
    ),
    (re.compile(r"rapor tarihi", re.IGNORECASE), ("ReportDate", "DataDate")),
    (
        re.compile(r"periyot|dönem|\bay\b|\(ay\)|aylık|ay sonu|çeyrek", re.IGNORECASE),
        ("Period", "PeriodId", "DataDate", "ReportDate"),
    ),
    (re.compile(r"yıl", re.IGNORECASE), ("Year", "Period", "DataDate")),
)


def present_columns(value: str, columns: Sequence[str]) -> list[str]:
    """The listed names the object has, in its own spelling, each once."""

    spelled = {c.casefold(): c for c in columns}
    kept: list[str] = []
    for name in split_terms(value):
        own = spelled.get(name.casefold())
        if own and own not in kept:
            kept.append(own)
    return kept


def date_key(grain: str, keys: list[str], times: list[str]) -> list[str]:
    """A grain cut by a date has that date among its keys."""

    folded_times = {t.casefold(): t for t in times}
    if any(k.casefold() in folded_times for k in keys):
        return keys
    for pattern, preferred in _GRAIN_TIME:
        if pattern.search(grain or ""):
            for name in preferred:
                if name.casefold() in folded_times:
                    return [*keys, folded_times[name.casefold()]]
    return keys


def align_object(
    record: dict[str, str], columns: Sequence[str], decisions: Decisions
) -> dict[str, str]:
    """The object fields that change, with their new values (the record itself is not touched)."""

    keys = present_columns(record.get("KeyColumns", ""), columns)
    times = present_columns(record.get("TimeColumns", ""), columns)
    keys = date_key(record.get("Grain", ""), keys, times)
    wanted = {
        "KeyColumns": ", ".join(keys),
        "TimeColumns": ", ".join(times),
        "BusinessDomain": decisions.domain(record.get("BusinessDomain", "")),
    }
    return {
        name: value
        for name, value in wanted.items()
        if value != (record.get(name) or "")
    }
