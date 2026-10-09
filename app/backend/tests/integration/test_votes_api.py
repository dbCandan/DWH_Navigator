"""Votes over HTTP and PostgreSQL (data-dictionary 006-answer-feedback Requirement 1-10, 14-18;
Acceptance 2, 3, 4).

The source's ``test_feedback``, ``test_answer_votes_drop_the_kept_answer`` and
``test_ask_carries_earlier_votes`` with signed-in users instead of browser ids, the request checks,
the keys from a question longer than 2000 characters, the saved answers deleted by a 👎 majority,
the overlay on answers and its failure, reports untouched by votes, the index read of one
question's votes, votes kept for years and no question, table or reason in the logs.
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from app.db.session import async_session_factory, engine
from app.domain.models.answer_vote import AnswerVote
from app.infrastructure.repositories.answer_vote_repository import question_votes
from app.services.analysis import feedback
from app.services.answer_feedback import AnswerVotes
from tests.fakes.telemetry import TelemetryCapture
from tests.integration.analysis import Qa, qa_harness, saved_answer_count
from tests.integration.conftest import RecordingHandler, SignedIn
from tests.integration.data_dictionary import DataDictionary, error, sql
from tests.parity import excel_dump

pytestmark = pytest.mark.integration

QUESTION = "kart limit doluluk"  # the fake analyst suggests five tables
MARKER = "QZXOYGEREKCE"


@pytest.fixture
async def qa(dd: DataDictionary) -> AsyncIterator[Qa]:
    await sql("DELETE FROM answer_vote")
    async for each in qa_harness(dd):
        yield each


async def vote(qa: Qa, who: SignedIn | None = None, **body: Any) -> Any:
    return await qa.request("POST", "/votes", who, json=body)


async def answered(qa: Qa, query: str = QUESTION, who: SignedIn | None = None) -> dict[str, Any]:
    analysis_id = await qa.started(query, who)
    done = await qa.finished(analysis_id, who)
    assert done["state"] == "completed", done
    return done


async def test_a_vote_is_stored_for_the_signed_in_user(qa: Qa) -> None:
    done = await answered(qa)
    best = done["result"]["objects"][0]["key"]
    response = await vote(qa, query=QUESTION, scope="table", table_key=best, vote="up")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {
        "votes": {"up": 1, "down": 0, "support": 0.333, "status": "approved", "reasons": []},
        "answer_rejected": False,
        "forgotten": 0,
    }
    rows = await sql(
        "SELECT v.scope, v.table_key, v.vote, v.text_key, v.query_text, u.public_id, "
        "v.dictionary_version, v.note FROM answer_vote v JOIN app_user u ON u.user_id = v.voter_id"
    )
    assert [tuple(r) for r in rows] == [
        (
            "table",
            best,
            "up",
            "kart limit doluluk",
            QUESTION,
            qa.user.public_id,
            qa.dd.index.engine().dictionary.version,
            None,
        )
    ]
    again = (await qa.job(done["analysis_id"]))["result"]
    shown = next(m for m in again["objects"] if m["key"] == best)
    assert shown["votes"]["status"] == "approved" and "score_before" in shown
    assert again["feedback"]["mine"] == {best: "up"}
    assert again["feedback"]["answer_at"].endswith("+03:00")


@pytest.mark.parametrize(
    "body",
    [
        {"query": QUESTION, "scope": "table", "vote": "up"},
        {"query": QUESTION, "scope": "table", "table_key": "", "vote": "up"},
        {"query": QUESTION, "scope": "answer", "table_key": "x", "vote": "up"},
        {"query": QUESTION, "scope": "answer", "vote": "maybe"},
        {"query": QUESTION, "scope": "object", "vote": "up"},
        {"query": "   ", "scope": "answer", "vote": "up"},
        {"query": "x" * 4001, "scope": "answer", "vote": "up"},
        {"query": QUESTION, "scope": "answer", "vote": "down", "note": "y" * 301},
        {"query": QUESTION, "scope": "answer", "vote": "down", "voter": "baska"},
        {"query": QUESTION, "scope": "answer", "vote": "up", "answer_at": "2026-10-09 10:00"},
        {"query": QUESTION, "scope": "table", "table_key": "t" * 301, "vote": "up"},
    ],
)
async def test_the_request_is_checked(qa: Qa, body: dict[str, Any]) -> None:
    assert error(await qa.request("POST", "/votes", json=body)) == (422, "invalid_request")
    assert await sql("SELECT count(*) FROM answer_vote") == [(0,)]


async def test_a_table_must_be_in_the_dictionary_and_a_reason_may_be_300(qa: Qa) -> None:
    unknown = await vote(qa, query=QUESTION, scope="table", table_key="SYNDM.yok.Tablo", vote="up")
    assert error(unknown) == (422, "vote_table_unknown")
    reason = await vote(qa, query=QUESTION, scope="answer", vote="down", note=" " + "y" * 300)
    assert reason.status_code == 201
    assert await sql("SELECT note FROM answer_vote") == [("y" * 300,)]
    long_query = await vote(qa, query="x" * 4000, scope="answer", vote="up")
    assert long_query.status_code == 201
    punctuation = await vote(
        qa,
        query="?!",
        scope="table",
        table_key=next(iter(qa.dd.index.engine().objects)),
        vote="up",
    )
    assert punctuation.json()["votes"] is None  # both keys of the question are empty


async def test_answer_votes_drop_the_kept_answer(qa: Qa) -> None:
    first = await answered(qa)
    assert await saved_answer_count() == 1
    one = await vote(qa, query=QUESTION, scope="answer", vote="down")
    assert one.json()["answer_rejected"] is False and one.json()["forgotten"] == 0
    two = await vote(qa, qa.other, query=QUESTION, scope="answer", vote="down")
    assert two.json()["answer_rejected"] is True and two.json()["forgotten"] == 1
    assert two.json()["votes"]["down"] == 2
    assert await saved_answer_count() == 0
    three = await vote(qa, qa.other, query=QUESTION, scope="answer", vote="down")
    assert three.json()["answer_rejected"] is True and three.json()["forgotten"] == 0
    asked_again = await answered(qa)
    assert asked_again["flow"] == "analyst" and asked_again["analysis_id"] != first["analysis_id"]


async def test_ask_carries_earlier_votes(qa: Qa) -> None:
    done = await answered(qa)
    best = done["result"]["objects"][0]["key"]
    for who in (qa.user, qa.other):
        response = await vote(
            qa, who, query=QUESTION, scope="table", table_key=best, vote="down", note="Konu farklı"
        )
        assert response.status_code == 201
    third = await qa.dd.auth.account(qa.dd.admin, "kullanici")
    again = await answered(qa, QUESTION.upper(), third)  # a saved answer, read by a third user
    result = again["result"]
    assert again["flow"] == "reused"
    assert best not in [m["key"] for m in result["objects"]]
    assert result["rejected"][0]["key"] == best
    assert result["rejected"][0]["votes"]["reasons"] == ["Konu farklı", "Konu farklı"]
    assert result["feedback"]["mine"] == {}
    mine = (await qa.job(done["analysis_id"]))["result"]["feedback"]["mine"]
    assert mine == {best: "down"}
    raw = json.dumps(result, ensure_ascii=False)
    for name in (qa.user.public_id, qa.other.public_id, qa.user.username, qa.other.username):
        assert name not in raw


async def test_the_keys_come_from_the_whole_long_question(qa: Qa) -> None:
    long_question = QUESTION + " " + " ".join(f"ek{i} kelime" for i in range(260))  # 2 tables
    assert 2000 < len(long_question) <= 4000
    done = await answered(qa, long_question)
    best = done["result"]["objects"][0]["key"]
    for who in (qa.user, qa.other):
        await vote(qa, who, query=long_question, scope="table", table_key=best, vote="down")
    again = (await qa.job(done["analysis_id"]))["result"]
    assert [m["key"] for m in again["rejected"]] == [best]


async def test_an_overlay_failure_returns_the_answer_without_votes(
    qa: Qa,
    monkeypatch: pytest.MonkeyPatch,
    telemetry_capture: TelemetryCapture,
    recorded_logs: RecordingHandler,
) -> None:
    done = await answered(qa)
    monkeypatch.setattr(feedback, "apply", lambda *args: 1 / 0)
    again = (await qa.job(done["analysis_id"]))["result"]
    assert again["feedback"] is None and again["rejected"] is None
    assert all(m["votes"] is None for m in again["objects"])
    assert [m["key"] for m in again["objects"]] == [m["key"] for m in done["result"]["objects"]]
    assert telemetry_capture.value("dwhnavigator_feedback_apply_failures_total") == 1
    assert recorded_logs.events("feedback.apply_failed")[0]["error_type"] == "ZeroDivisionError"


async def test_votes_change_neither_the_report_nor_the_record(qa: Qa) -> None:
    done = await answered(qa)
    analysis_id = done["analysis_id"]
    before = await qa.request("GET", f"/analyses/{analysis_id}/report")
    record_before = await sql(
        "SELECT result FROM analysis_record WHERE public_id = :p", p=analysis_id
    )
    best = done["result"]["objects"][0]["key"]
    for who in (qa.user, qa.other):
        await vote(qa, who, query=QUESTION, scope="table", table_key=best, vote="down")
    after = await qa.request("GET", f"/analyses/{analysis_id}/report")
    assert excel_dump.workbook(before.content) == excel_dump.workbook(after.content)
    assert record_before == await sql(
        "SELECT result FROM analysis_record WHERE public_id = :p", p=analysis_id
    )


async def test_one_question_is_read_through_the_key_indexes(qa: Qa) -> None:
    """With five thousand votes of other questions the plan reads both key indexes only."""

    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            tenant_id, voter_id = (
                await connection.execute(
                    text("SELECT home_tenant_id, user_id FROM app_user WHERE public_id = :p"),
                    {"p": qa.user.public_id},
                )
            ).one()
            await connection.execute(
                text(
                    "INSERT INTO answer_vote (tenant_id, voter_id, query_text, text_key, "
                    "meaning_key, scope, vote, dictionary_version) SELECT :t, :u, 'q', "
                    "'soru ' || g, CASE WHEN g % 3 = 0 THEN '' ELSE 'anlam ' || (g % 500) END, "
                    "'answer', 'up', 'v' FROM generate_series(1, 5000) g"
                ),
                {"t": tenant_id, "u": voter_id},
            )
            await connection.execute(text("ANALYZE answer_vote"))
            statement = question_votes(tenant_id, "soru 7", "anlam 7")
            assert statement is not None
            compiled = statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
            plan = "\n".join(
                str(row[0]) for row in await connection.execute(text(f"EXPLAIN {compiled}"))
            )
        finally:
            await transaction.rollback()
    assert "ix_answer_vote_tenant_text_key" in plan
    assert "ix_answer_vote_tenant_meaning_key" in plan
    assert "Seq Scan on answer_vote" not in plan
    assert question_votes(1, "", "") is None


async def test_old_votes_stay_and_weigh_by_their_age(qa: Qa) -> None:
    done = await answered(qa)
    best = done["result"]["objects"][0]["key"]
    engine_now = qa.dd.index.engine()
    keys = engine_now.cache_keys(QUESTION)
    users = await sql(
        "SELECT user_id, home_tenant_id FROM app_user WHERE public_id = :p", p=qa.other.public_id
    )
    user_id, tenant_id = users[0]
    async with async_session_factory() as session:
        session.add(
            AnswerVote(
                tenant_id=tenant_id,
                voter_id=user_id,
                created_at=datetime.now(UTC) - timedelta(days=730),
                query_text=QUESTION,
                text_key=keys[0],
                meaning_key=keys[1],
                scope="table",
                table_key=best,
                vote="up",
                dictionary_version=engine_now.dictionary.version,
            )
        )
        await session.commit()
    restarted = AnswerVotes(
        index=qa.dd.index,
        session_factory=async_session_factory,
        saved_answers=qa.jobs.saved_answers,
    )
    qa.jobs.overlay = restarted
    shown = (await qa.job(done["analysis_id"]))["result"]
    tally = next(m for m in shown["objects"] if m["key"] == best)["votes"]
    weight = 0.5 ** (730 / 180)
    assert tally["up"] == 1 and tally["support"] == round(weight / (weight + 2), 3)
    assert await sql("SELECT count(*) FROM answer_vote") == [(1,)]


async def test_logs_and_metrics_carry_no_question_table_or_reason(
    qa: Qa, recorded_logs: RecordingHandler, telemetry_capture: TelemetryCapture
) -> None:
    done = await answered(qa)
    best = done["result"]["objects"][0]["key"]
    await vote(qa, query=QUESTION, scope="table", table_key=best, vote="down", note=MARKER)
    await vote(qa, query=QUESTION, scope="answer", vote="down", note=MARKER)
    await vote(qa, qa.other, query=QUESTION, scope="answer", vote="down")
    recorded = recorded_logs.events("feedback.vote_recorded")
    assert [(e["scope"], e["vote"], e["has_note"]) for e in recorded] == [
        ("table", "down", True),
        ("answer", "down", True),
        ("answer", "down", False),
    ]
    assert recorded[0]["user_public_id"] == qa.user.public_id
    assert recorded_logs.events("feedback.saved_answers_forgotten") == [
        {"event": "feedback.saved_answers_forgotten", "count": 1}
    ]
    votes = {
        (labels["scope"], labels["vote"]): value
        for labels, value in telemetry_capture.points("dwhnavigator_feedback_votes_total")
    }
    assert votes == {("table", "down"): 1, ("answer", "down"): 2}
    assert telemetry_capture.value("dwhnavigator_feedback_saved_answers_forgotten_total") == 1
    everything = recorded_logs.rendered() + json.dumps(
        [dict(s.attributes or {}) for s in telemetry_capture.spans()], ensure_ascii=False
    )
    for secret in (MARKER, QUESTION, best, "doluluk"):
        assert secret not in everything, secret
