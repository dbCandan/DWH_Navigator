"""The added weighting tests of data-dictionary 006-answer-feedback (Test stratejisi): the exact
thresholds, the last vote across text and meaning matches, the newest three reasons, the order of
endorsed tables, the level after the nudge, the 0..1 bound, an answer vote in the answer's own
minute; and the stored votes and answer times as the weighting reads them."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.infrastructure.repositories.answer_vote_repository import VoteRow
from app.services.analysis.feedback import FeedbackView, Tally, apply, assess
from app.services.answer_feedback import answer_since, answer_written_at, assess_rows

pytestmark = pytest.mark.unit

NOW = datetime.fromisoformat("2026-10-01T12:00:00")


def vote(obj: str, v: str, who: str, *, key: str = "t", meaning: str = "m",
         at: str = "2026-10-01T12:00:00", scope: str = "object", note: str = "",
         dv: str = "") -> dict[str, Any]:  # fmt: skip
    return {"at": at, "text_key": key, "meaning_key": meaning, "object": obj, "vote": v,
            "voter": who, "scope": scope, "note": note, "dictionary_version": dv}  # fmt: skip


def match(key: str, score: float, level: str = "Orta") -> dict[str, Any]:
    return {"key": key, "name": key, "score": score, "level": level, "rank": 0}


def test_the_exact_thresholds() -> None:
    # down exactly 1.5 (1.0 + 0.5 on another dictionary version) rejects; just below only doubts.
    rows = [vote("A", "down", "u1", dv="v1"), vote("A", "down", "u2", dv="v0")]
    tally = assess(rows, "t", dictionary_version="v1", now=NOW).objects["A"]
    assert tally.down == 1.5 and tally.status == "rejected"
    assert Tally(down=1.4999).status == "doubted"
    # support exactly -0.3 rejects; exactly 0.2 approves.
    assert Tally(up=0.75, down=2.25).support == -0.3
    assert Tally(up=0.75, down=2.25).status == "rejected"
    assert Tally(up=0.76, down=2.25).status == "disputed"
    assert Tally(up=1.25, down=0.5).support == 0.2
    assert Tally(up=1.25, down=0.5).status == "approved"
    assert Tally(up=1.24, down=0.5).status == "disputed"
    # a share of exactly 0.6 rejects the whole answer.
    assert FeedbackView(answer=Tally(up=1.0, down=1.5)).answer_rejected is True
    assert FeedbackView(answer=Tally(up=1.01, down=1.5)).answer_rejected is False
    assert FeedbackView(answer=Tally(up=0.0, down=1.49)).answer_rejected is False


def test_the_last_vote_across_text_and_meaning_matches_counts() -> None:
    rows = [
        vote("A", "up", "u1", key="t", at="2026-10-01T11:00:00"),
        vote("A", "down", "u1", key="other", meaning="m", at="2026-10-01T12:00:00"),
    ]
    tally = assess(rows, "t", "m", now=NOW).objects["A"]
    assert (tally.people_up, tally.people_down, tally.up, tally.down) == (0, 1, 0.0, 0.6)


def test_the_newest_three_reasons() -> None:
    rows = [
        vote("A", "down", f"u{i}", at=f"2026-10-01T1{i}:00:00", note=f"gerekçe {i}")
        for i in range(5)
    ]
    assert assess(rows, "t", now=NOW).objects["A"].to_dict()["reasons"] == [
        "gerekçe 4",
        "gerekçe 3",
        "gerekçe 2",
    ]


def test_endorsed_tables_by_support() -> None:
    rows = [
        vote("B", "up", "u1"),
        vote("C", "up", "u1"),
        vote("C", "up", "u2"),
    ]
    known = {"B": {"name": "b", "schema": "s"}, "C": {"name": "c", "schema": "s"}}
    out = apply({"objects": [], "near": []}, assess(rows, "t", now=NOW), known)
    assert [e["key"] for e in out["endorsed"]] == ["C", "B"]
    assert out["endorsed"][0] == {
        "name": "c",
        "schema": "s",
        "key": "C",
        "votes": out["endorsed"][0]["votes"],
    }


def test_the_nudge_changes_the_level_and_stays_within_0_and_1() -> None:
    rows = [vote("A", "up", f"u{i}") for i in range(6)] + [
        vote("B", "up", f"u{i}") for i in range(6)
    ]
    out = apply(
        {"objects": [match("A", 0.79), match("B", 0.99)], "near": []},
        assess(rows, "t", now=NOW),
        {},
    )
    shown = {m["key"]: m for m in out["objects"]}
    assert shown["A"]["score_before"] == 0.79 and shown["A"]["score"] > 0.8
    assert shown["A"]["level"] == "Yüksek"
    assert shown["B"]["score"] == 1.0


def test_an_answer_vote_in_the_answers_own_minute_counts() -> None:
    rows = [
        vote("", "down", "u1", scope="answer", at="2026-10-01T09:14:59"),
        vote("", "down", "u2", scope="answer", at="2026-10-01T09:15:00"),
        vote("", "down", "u3", scope="answer", at="2026-10-01T09:15:59"),
    ]
    view = assess(rows, "t", answer_since="2026-10-01T09:15", now=NOW)
    assert view.answer.people_down == 2


def test_stored_votes_and_answer_times_as_the_weighting_reads_them() -> None:
    at = datetime(2026, 10, 1, 9, 15, 7, 123456, tzinfo=UTC)
    rows = assess_rows(
        [
            VoteRow("p1", at, "t", "m", "table", "A.B.C", "down", "neden", "v1"),
            VoteRow("p2", at, "t", "", "answer", None, "up", None, "v1"),
        ]
    )
    assert rows == [
        {"at": "2026-10-01T09:15:07", "text_key": "t", "meaning_key": "m", "scope": "object",
         "object": "A.B.C", "vote": "down", "note": "neden", "voter": "p1",
         "dictionary_version": "v1"},
        {"at": "2026-10-01T09:15:07", "text_key": "t", "meaning_key": "", "scope": "answer",
         "object": "", "vote": "up", "note": "", "voter": "p2", "dictionary_version": "v1"},
    ]  # fmt: skip
    written = answer_written_at("2026-10-01 12:15")
    assert written is not None and written.isoformat() == "2026-10-01T12:15:00+03:00"
    assert answer_since(written) == "2026-10-01T09:15"
    assert answer_written_at("") is None and answer_since(None) == ""
