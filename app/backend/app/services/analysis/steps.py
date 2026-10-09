"""An analysis job's steps as its record keeps them (analysis-records Requirement 3, Decision 9).

Pure: the trace's spans become at most 500 steps with their limits applied; the six phase
durations come from the step keys and the model use from the call summaries of the ``llm`` steps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

MAX_STEPS = 500
NAME_CHARS = 120
DETAIL_CHARS = 300

# The six phases in display order and the step keys counted for each (Requirement 3).
PHASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("queue", ("queue",)),
    ("saved_answer_lookup", ("saved_answer_lookup",)),
    ("model_check", ("model_check",)),
    ("rule_hints", ("rule_hints",)),
    ("analyst_pick", ("shortlist", "family_search")),
    ("analyst_write", ("analyst_report",)),
)
PHASE_NAMES = tuple(name for name, _ in PHASES)
STEP_KEYS = frozenset(key for _, keys in PHASES for key in keys)
KINDS = frozenset({"step", "llm", "event"})
STATUSES = frozenset({"ok", "warn", "error"})


@dataclass(frozen=True, slots=True)
class RecordedSteps:
    steps: list[dict[str, Any]]
    truncated: bool
    phases: dict[str, int]
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int


def _int(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def step_of(span: dict[str, Any]) -> dict[str, Any]:
    """One span of ``Trace.to_list`` in the record's step form, its texts cut at the limits."""

    kind = span["kind"] if span["kind"] in KINDS else "event"
    status = span["status"] if span["status"] in STATUSES else "error"
    key = span.get("key", "")
    step: dict[str, Any] = {
        "seq": _int(span["id"]),
        "parent": span["parent"] if isinstance(span["parent"], int) else None,
        "name": str(span["name"])[:NAME_CHARS],
        "kind": kind,
        "key": key if key in STEP_KEYS else None,
        "start_ms": max(0, _int(span["start_ms"])),
        "ms": max(0, _int(span["ms"])),
        "status": status,
        "detail": str(span.get("detail", ""))[:DETAIL_CHARS],
    }
    data = span.get("data") or {}
    if kind == "llm" and isinstance(data.get("call"), dict):
        step["call"] = data["call"]
    if isinstance(data.get("check"), dict):
        step["check"] = data["check"]
    return step


def record_steps(spans: Sequence[dict[str, Any]]) -> RecordedSteps:
    """The steps to store, the phase durations and the model use of the whole trace."""

    every = [step_of(span) for span in spans]
    phases = {name: 0 for name in PHASE_NAMES}
    for name, keys in PHASES:
        phases[name] = sum(s["ms"] for s in every if s["kind"] == "step" and s["key"] in keys)
    calls = [s for s in every if s["kind"] == "llm"]
    return RecordedSteps(
        steps=every[:MAX_STEPS],
        truncated=len(every) > MAX_STEPS,
        phases=phases,
        llm_calls=len(calls),
        prompt_tokens=sum(_int(s.get("call", {}).get("prompt_tokens")) for s in calls),
        completion_tokens=sum(_int(s.get("call", {}).get("completion_tokens")) for s in calls),
    )
