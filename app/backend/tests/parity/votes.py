"""The vote weighting's parity data (006-answer-feedback Requirement 17 and Test strategy).

    python -B -m tests.parity.votes source   # with the source copy's src on the path
    python -B -m tests.parity.votes target

Generated vote row sets (people, tables, answer votes, text and meaning matches, ages, future and
unreadable times, dictionary versions, reasons, answer times) and answers (suggestions, near
candidates, the dictionary's known tables) go through ``assess`` and ``apply`` of one side with a
fixed "now"; every view and every shaped answer is printed as a digest, the first ones in full. The
voter is a user id, as the target stores it. The source side's output is the committed snapshot
``votes.json``.
"""

from __future__ import annotations

import json
import logging
import random
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from tests.parity import dump

NOW = datetime.fromisoformat("2026-10-08T12:00:00")
SCENARIOS = 400
FULL = 12
KEYS = [f"SYNDM.S.vTablo{i}" for i in range(1, 11)]
VOTERS = [f"user-{i}" for i in range(1, 8)]
TEXT_KEYS = ["kart limit doluluk", "musteri yasi"]
MEANING_KEYS = ["kavram:kart|kavram:limit", "", "kavram:yas"]
NOTES = ["", "", "Konu farklı", "Gereken kolon yok", "Eski / kullanılmıyor", "Doğru ama yetersiz"]
LEVELS = ["Yüksek", "Orta", "Düşük"]


def _time(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.05:
        return "okunamaz"
    if roll < 0.1:
        return "2026-10-09T08:00:00"  # in the future
    minutes = rng.choice([0, 1, 59, 60 * 24, 60 * 24 * 90, 60 * 24 * 180, 60 * 24 * 400])
    second = rng.randrange(60)
    stamp = NOW - timedelta(minutes=minutes, seconds=second)
    return stamp.isoformat(timespec="seconds")


def _row(rng: random.Random) -> dict[str, Any]:
    scope = "answer" if rng.random() < 0.3 else "object"
    return {
        "at": _time(rng),
        "text_key": rng.choice(TEXT_KEYS + ["baska soru"]),
        "meaning_key": rng.choice(MEANING_KEYS),
        "scope": scope,
        "object": "" if scope == "answer" else rng.choice(KEYS),
        "vote": rng.choice(["up", "down", "down"]),
        "note": rng.choice(NOTES),
        "voter": rng.choice(VOTERS),
        "dictionary_version": rng.choice(["abc123-1557", "abc123-1557", "eski00-1500"]),
    }


def _match(rng: random.Random, key: str) -> dict[str, Any]:
    score = rng.choice([0.5, 0.62, 0.79, 0.8, 0.95, 0.99, 1.0, round(rng.random(), 4)])
    return {
        "rank": 0,
        "key": key,
        "name": key.rsplit(".", 1)[-1],
        "schema": "SYNDM.S",
        "score": score,
        "level": rng.choice(LEVELS),
        "columns": [],
    }


def _answer(rng: random.Random) -> dict[str, Any]:
    keys = rng.sample(KEYS, rng.randrange(0, 7))
    near = [k for k in KEYS if k not in keys][: rng.randrange(0, 3)]
    return {
        "query": "soru",
        "verdict": "VAR",
        "objects": [_match(rng, k) for k in keys],
        "near": [_match(rng, k) for k in near],
    }


def scenarios() -> list[dict[str, Any]]:
    rng = random.Random("answer-feedback-parity")
    out = []
    for n in range(SCENARIOS):
        rows = [_row(rng) for _ in range(rng.randrange(0, 30))]
        known = {k: {"name": k.rsplit(".", 1)[-1], "schema": "SYNDM.S"} for k in KEYS[:8]}
        out.append(
            {
                "id": f"v{n:03d}",
                "rows": rows,
                "text_key": rng.choice(TEXT_KEYS + [""]),
                "meaning_key": rng.choice(MEANING_KEYS),
                "dictionary_version": rng.choice(["abc123-1557", "", "eski00-1500"]),
                "voter": rng.choice(VOTERS + [""]),
                "answer_since": rng.choice(["", "", "2026-10-08T11:59", "2026-10-07T12:00"]),
                "answer": _answer(rng),
                "known": known,
            }
        )
    return out


def _view(view: Any) -> dict[str, Any]:
    return {
        "objects": {
            k: {**t.to_dict(), "w": [t.up, t.down]} for k, t in sorted(view.objects.items())
        },
        "answer": {**view.answer.to_dict(), "w": [view.answer.up, view.answer.down]},
        "answer_rejected": view.answer_rejected,
        "mine": dict(view.mine),
    }


def _collect(assess: Callable[..., Any], apply: Callable[..., Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for n, s in enumerate(scenarios()):
        view = assess(
            [dict(r) for r in s["rows"]],
            s["text_key"],
            s["meaning_key"],
            dictionary_version=s["dictionary_version"],
            voter=s["voter"],
            answer_since=s["answer_since"],
            now=NOW,
        )
        shaped = apply(json.loads(json.dumps(s["answer"])), view, s["known"])
        data = {"view": _view(view), "answer": shaped}
        results[s["id"]] = data if n < FULL else dump.digest(data)
    return {"scenarios": len(results), "results": results}


def collect(side: str) -> dict[str, Any]:
    if side == "source":
        from vsa.feedback import apply, assess
    else:
        from app.services.analysis.feedback import (  # type: ignore[assignment]
            apply,
            assess,
        )
    return _collect(assess, apply)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)  # the engines log names they drop; nothing to see here
    json.dump(collect(sys.argv[1]), sys.stdout, ensure_ascii=False, sort_keys=True, indent=1)
    sys.stdout.write("\n")
