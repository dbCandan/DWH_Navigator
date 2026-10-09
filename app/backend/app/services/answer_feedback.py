"""Votes on answers and their overlay (data-dictionary 006-answer-feedback Requirement 1-10, 14-18).

A vote is stored as one appended row for the signed-in user; the question's keys are computed here
from its full text with the serving engine (the functions saved answers use). Reading an answer,
the votes cast on the same question or (when not empty) on one meaning the same are weighed by the
source's ``feedback.assess`` and laid over the answer by ``feedback.apply`` for the reading user;
the analysis, its saved answer, its record and its reports never change. When enough people find a
whole answer useless its saved answers are deleted through question-analysis's service.

Vote times are UTC; the weighting compares them as the source compared its times, as ISO texts
at second precision, and an answer's time at minute precision (Requirement 6).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import telemetry
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.domain.models.answer_vote import AnswerVote
from app.infrastructure.repositories.answer_vote_repository import (
    AnswerVoteRepository,
    VoteRow,
)
from app.services.analysis import feedback
from app.services.analysis.jobs import OverlayContext
from app.services.analysis.pipeline import ISTANBUL, Engine
from app.services.analysis.saved_answers import SavedAnswers
from app.services.search_index import SearchIndex, search_index_not_ready

logger = logging.getLogger("app.feedback")

SCOPE_TABLE = "table"
SCOPE_ANSWER = "answer"
_ASSESS_SCOPE = {SCOPE_TABLE: "object", SCOPE_ANSWER: "answer"}


def vote_table_unknown() -> ApplicationError:
    return ApplicationError(
        422,
        "vote_table_unknown",
        "Bu tablo artık sözlükte yok; cevabı yenileyip yeniden deneyin.",
    )


def _utc_text(at: datetime, timespec: str) -> str:
    """A UTC time as the naive ISO text the source compared (``seconds`` or ``minutes``)."""

    return at.astimezone(UTC).replace(tzinfo=None).isoformat(timespec=timespec)


def assess_rows(rows: list[VoteRow]) -> list[dict[str, Any]]:
    """Stored votes in the row form of the source's ``feedback.jsonl`` that ``assess`` reads."""

    return [
        {
            "at": _utc_text(r.created_at, "seconds"),
            "text_key": r.text_key,
            "meaning_key": r.meaning_key,
            "scope": _ASSESS_SCOPE[r.scope],
            "object": r.table_key or "",
            "vote": r.vote,
            "note": r.note or "",
            "voter": r.voter,
            "dictionary_version": r.dictionary_version,
        }
        for r in rows
    ]


def answer_written_at(generated_at: str) -> datetime | None:
    """When an answer was written: its Istanbul ``generated_at`` (``YYYY-MM-DD HH:MM``) as a time
    with its zone; a saved answer given again keeps its first analysis's time."""

    try:
        return datetime.fromisoformat(generated_at).replace(tzinfo=ISTANBUL)
    except (TypeError, ValueError):
        return None


def answer_since(written_at: datetime | None) -> str:
    """The minute an answer was written, as ``assess`` compares it; "" counts every answer vote."""

    return _utc_text(written_at, "minutes") if written_at is not None else ""


def known_tables(engine: Engine) -> dict[str, dict[str, Any]]:
    """Every table of the current dictionary with its name and schema (the source's ``_known``)."""

    known: dict[str, dict[str, Any]] = {}
    for key, obj in engine.objects.items():
        first = obj.features[0].col
        known[key] = {"name": first.object_name, "schema": f"{first.database}.{first.schema}"}
    return known


@dataclass(frozen=True, slots=True)
class VoteOutcome:
    votes: dict[str, Any] | None
    answer_rejected: bool
    forgotten: int


class AnswerVotes:
    """Recording votes and laying them over answers."""

    def __init__(
        self,
        *,
        index: SearchIndex,
        session_factory: async_sessionmaker[AsyncSession],
        saved_answers: SavedAnswers,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.index = index
        self._session_factory = session_factory
        self.saved_answers = saved_answers
        self._clock = clock

    def _engine(self) -> Engine:
        if not self.index.is_serving:
            raise search_index_not_ready()
        return self.index.engine()

    async def _view(
        self,
        tenant_id: int,
        engine: Engine,
        keys: tuple[str, str],
        voter: str,
        since: str,
    ) -> feedback.FeedbackView:
        async with self._session_factory() as session:
            rows = await AnswerVoteRepository(session).for_question(tenant_id, *keys)
        return feedback.assess(
            assess_rows(rows),
            keys[0],
            keys[1],
            dictionary_version=engine.dictionary.version,
            voter=voter,
            answer_since=since,
            now=self._clock().astimezone(UTC).replace(tzinfo=None),
        )

    # ------------------------------------------------------------------ recording

    async def record(
        self,
        *,
        tenant_id: int,
        voter_id: int,
        voter_public_id: str,
        query: str,
        scope: str,
        table_key: str | None,
        vote: str,
        note: str | None,
        answer_at: datetime | None,
    ) -> VoteOutcome:
        """Requirement 1, 2, 10: store the vote, tally it, delete the question's saved answers
        when the whole answer is now rejected."""

        engine = self._engine()
        keys: tuple[str, str] = await asyncio.to_thread(engine.cache_keys, query)
        if scope == SCOPE_TABLE and table_key not in engine.objects:
            raise vote_table_unknown()
        async with self._session_factory() as session:
            await AnswerVoteRepository(session).add(
                AnswerVote(
                    tenant_id=tenant_id,
                    voter_id=voter_id,
                    created_at=self._clock(),
                    query_text=query,
                    text_key=keys[0],
                    meaning_key=keys[1],
                    scope=scope,
                    table_key=table_key if scope == SCOPE_TABLE else None,
                    vote=vote,
                    note=note,
                    dictionary_version=engine.dictionary.version[:64],
                    created_by=voter_id,
                )
            )
            await session.commit()
        telemetry.record_feedback_vote(scope, vote)
        log_event(
            logger,
            "feedback.vote_recorded",
            scope=scope,
            vote=vote,
            has_note=bool(note),
            user_public_id=voter_public_id,
        )
        view = await self._view(tenant_id, engine, keys, voter_public_id, answer_since(answer_at))
        forgotten = 0
        if scope == SCOPE_ANSWER and view.answer_rejected:
            forgotten = await self.saved_answers.forget(tenant_id, *keys)
            if forgotten:
                telemetry.record_feedback_saved_answers_forgotten(forgotten)
                log_event(logger, "feedback.saved_answers_forgotten", count=forgotten)
        tally = view.answer if scope == SCOPE_ANSWER else view.objects.get(table_key or "")
        return VoteOutcome(
            votes=tally.to_dict() if tally else None,
            answer_rejected=view.answer_rejected,
            forgotten=forgotten,
        )

    # ------------------------------------------------------------------ the overlay

    async def apply(self, answer: dict[str, Any], context: OverlayContext) -> dict[str, Any]:
        """question-analysis's overlay point (Requirement 7, 8): the answer as the votes on its
        question shape it for the reading user. A failure is logged with its class and counted,
        then raised so the caller returns the answer without votes."""

        try:
            engine = self._engine()
            keys: tuple[str, str] = await asyncio.to_thread(engine.cache_keys, context.query)
            written_at = answer_written_at(context.generated_at)
            view = await self._view(
                context.tenant_id, engine, keys, context.user_public_id, answer_since(written_at)
            )
            out = feedback.apply(answer, view, known_tables(engine))
            out["feedback"]["answer_at"] = written_at.isoformat() if written_at else None
        except Exception as error:
            telemetry.record_feedback_apply_failure()
            log_event(logger, "feedback.apply_failed", error_type=type(error).__name__)
            raise
        return out
