"""Reading earlier votes into the answer shown (ADR-036)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from vsa.feedback import apply, assess

NOW = datetime(2026, 10, 1, 12, 0)


def vote(obj: str, v: str, who: str, *, key: str = "t", meaning: str = "m",
         at: str = "2026-10-01T12:00:00", scope: str = "object", note: str = "",
         dv: str = "") -> dict[str, Any]:  # fmt: skip
    return {"at": at, "text_key": key, "meaning_key": meaning, "object": obj, "vote": v,
            "voter": who, "scope": scope, "note": note, "dictionary_version": dv}  # fmt: skip


def match(key: str, score: float) -> dict[str, Any]:
    return {"key": key, "name": key.split(".")[-1], "score": score, "level": "Orta", "rank": 0}


def answer(*objs: dict[str, Any], near: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"query": "q", "objects": list(objs), "near": near or []}


def test_latest_vote_of_a_person_counts_once() -> None:
    late = "2026-10-01T12:30:00"
    rows = [vote("A", "up", "u1"), vote("A", "up", "u1"), vote("A", "down", "u1", at=late)]
    t = assess(rows, "t", now=NOW).objects["A"]
    assert (t.people_up, t.people_down) == (0, 1)


def test_one_down_vote_only_doubts() -> None:
    t = assess([vote("A", "down", "u1")], "t", now=NOW).objects["A"]
    assert t.status == "doubted"


def test_two_people_reject_and_table_leaves_the_suggestions() -> None:
    rows = [vote("A", "down", "u1", note="konu farklı"), vote("A", "down", "u2")]
    view = assess(rows, "t", now=NOW)
    assert view.objects["A"].status == "rejected"
    out = apply(answer(match("A", 0.9), match("B", 0.7)), view, {})
    assert [m["key"] for m in out["objects"]] == ["B"]
    assert out["objects"][0]["rank"] == 1
    assert out["rejected"][0]["key"] == "A"
    assert out["rejected"][0]["votes"]["reasons"] == ["konu farklı"]


def test_support_nudges_confidence_and_reranks() -> None:
    rows = [vote("B", "up", "u1"), vote("B", "up", "u2"), vote("A", "down", "u3")]
    out = apply(answer(match("A", 0.80), match("B", 0.78)), assess(rows, "t", now=NOW), {})
    assert [m["key"] for m in out["objects"]] == ["B", "A"]
    b = out["objects"][0]
    assert b["score"] > b["score_before"] == 0.78
    assert b["votes"]["status"] == "approved"


def test_approved_near_candidate_is_promoted() -> None:
    view = assess([vote("N", "up", "u1")], "t", now=NOW)
    out = apply(answer(match("A", 0.8), near=[match("N", 0.4)]), view, {})
    keys = [m["key"] for m in out["objects"]]
    assert "N" in keys and out["objects"][keys.index("N")]["promoted"]
    assert out["near"] == []


def test_endorsed_tables_only_when_the_dictionary_has_them() -> None:
    view = assess([vote("X", "up", "u1"), vote("GONE", "up", "u1")], "t", now=NOW)
    known = {"X": {"name": "X", "schema": "DB.S", "groups": []}}
    out = apply(answer(match("A", 0.8)), view, known)
    assert [e["key"] for e in out["endorsed"]] == ["X"]


def test_similar_question_old_vote_and_other_dictionary_weigh_less() -> None:
    same = assess([vote("A", "up", "u1")], "t", now=NOW).objects["A"].up
    similar = assess([vote("A", "up", "u1", key="other")], "t", "m", now=NOW).objects["A"].up
    old = assess([vote("A", "up", "u1", at="2026-04-04T12:00:00")], "t", now=NOW).objects["A"].up
    other_dict = assess([vote("A", "up", "u1", dv="v1")], "t", dictionary_version="v2", now=NOW)
    assert same == 1.0 and similar == 0.6
    assert 0.45 < old < 0.55  # half-life 180 days
    assert other_dict.objects["A"].up == 0.5


def test_unrelated_question_is_ignored() -> None:
    view = assess([vote("A", "up", "u1", key="x", meaning="y")], "t", "m", now=NOW)
    assert not view.objects


def test_answer_rejected_needs_two_people_and_a_majority() -> None:
    one = [vote("", "down", "u1", scope="answer")]
    assert not assess(one, "t", now=NOW).answer_rejected
    two = [*one, vote("", "down", "u2", scope="answer")]
    assert assess(two, "t", now=NOW).answer_rejected
    mixed = [*two, vote("", "up", "u3", scope="answer"), vote("", "up", "u4", scope="answer")]
    assert not assess(mixed, "t", now=NOW).answer_rejected


def test_mine_holds_this_voters_votes() -> None:
    rows = [vote("A", "up", "me"), vote("", "down", "me", scope="answer"), vote("B", "up", "you")]
    assert assess(rows, "t", voter="me", now=NOW).mine == {"A": "up", "": "down"}


def test_no_votes_leaves_the_answer_as_is() -> None:
    data = answer(match("A", 0.8))
    out = apply(data, assess([], "t", now=NOW), {})
    assert out["objects"][0]["score"] == 0.8 and out["rejected"] == [] and out["endorsed"] == []


def test_answer_votes_judge_one_answer_not_the_question() -> None:
    old = [vote("", "down", f"u{i}", scope="answer", at="2026-09-01T10:00:00") for i in range(3)]
    assert assess(old, "t", now=NOW).answer_rejected
    fresh = assess(old, "t", answer_since="2026-09-02 08:00", voter="u1", now=NOW)
    assert not fresh.answer_rejected and fresh.mine == {}
