"""Persistence of votes (data-dictionary 006-answer-feedback Requirement 1, 3, 18, Decision 3).

Rows are only inserted. A question's votes are read through the tenant's text-key index and the
partial meaning-key index (only non-empty keys), never by reading the whole table.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.answer_vote import AnswerVote
from app.domain.models.user import User
from app.domain.models.visitor import Visitor


@dataclass(frozen=True, slots=True)
class VoteRow:
    """One stored vote as the weighting reads it; ``voter`` is the public_id of the voting
    account or visitor (003-anonymous-visitor Decision 5)."""

    voter: str
    created_at: datetime
    text_key: str
    meaning_key: str
    scope: str
    table_key: str | None
    vote: str
    note: str | None
    dictionary_version: str


class AnswerVoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, vote: AnswerVote) -> None:
        self.session.add(vote)
        await self.session.flush()

    async def for_question(self, tenant_id: int, text_key: str, meaning_key: str) -> list[VoteRow]:
        """The votes cast on this question's words or (when not empty) on its meaning, in vote
        time order, ties in insertion order; none when both keys are empty."""

        statement = question_votes(tenant_id, text_key, meaning_key)
        if statement is None:
            return []
        return [VoteRow(*row) for row in (await self.session.execute(statement)).all()]


def question_votes(tenant_id: int, text_key: str, meaning_key: str) -> Select[Any] | None:
    """The read of one question's votes through the two key indexes (Requirement 18)."""

    matches = []
    if text_key:
        matches.append(AnswerVote.text_key == text_key)
    if meaning_key:
        matches.append(and_(AnswerVote.meaning_key == meaning_key, AnswerVote.meaning_key != ""))
    if not matches:
        return None
    return (
        select(
            func.coalesce(User.public_id, Visitor.public_id),
            AnswerVote.created_at,
            AnswerVote.text_key,
            AnswerVote.meaning_key,
            AnswerVote.scope,
            AnswerVote.table_key,
            AnswerVote.vote,
            AnswerVote.note,
            AnswerVote.dictionary_version,
        )
        .outerjoin(User, User.user_id == AnswerVote.voter_id)
        .outerjoin(Visitor, Visitor.visitor_id == AnswerVote.voter_visitor_id)
        .where(AnswerVote.tenant_id == tenant_id, or_(*matches))
        .order_by(AnswerVote.created_at, AnswerVote.answer_vote_id)
    )
