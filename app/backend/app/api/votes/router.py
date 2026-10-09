"""Vote endpoint (data-dictionary/PRDs/006-answer-feedback, API sözleşmesi).

Open to ``kullanici`` and ``yonetici``; the voter is the signed-in user, re-read from the database
(Decision 2). No question, table key or reason reaches a log, a metric or a trace.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_role
from app.db.session import get_db
from app.domain.accounts import ROLE_USER
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.errors import error_responses
from app.schemas.votes.votes import VoteIn, VoteRecorded
from app.services.answer_feedback import AnswerVotes
from app.services.request_scope import acting_user_with_role, active_tenant

router = APIRouter(
    tags=["votes"],
    dependencies=[Depends(require_role(ROLE_USER))],
    responses=error_responses(
        {
            401: "not_authenticated: oturum yok",
            403: "forbidden: rol yok; cross_site_request: istek başka bir siteden geldi",
        }
    ),
)


def get_answer_votes(request: Request) -> AnswerVotes:
    votes: AnswerVotes = request.app.state.answer_votes
    return votes


@router.post(
    "/votes",
    status_code=status.HTTP_201_CREATED,
    response_model=VoteRecorded,
    responses=error_responses(
        {
            422: "invalid_request: biçim ya da bilinmeyen alan; vote_table_unknown: tablo sözlükte "
            "yok",
            503: "search_index_not_ready: ilk arama indeksi kuruluyor",
        }
    ),
)
async def cast_vote(
    body: VoteIn,
    context: CurrentContext,
    session: Annotated[AsyncSession, Depends(get_db)],
    votes: Annotated[AnswerVotes, Depends(get_answer_votes)],
) -> VoteRecorded:
    """Record a 👍/👎; the last vote of each person counts. Enough 👎 on the whole answer delete
    the question's saved answers, so it is analysed anew."""

    users = UserRepository(session)
    actor = await acting_user_with_role(users, context, ROLE_USER)
    tenant = await active_tenant(users, context)
    await session.commit()
    outcome = await votes.record(
        tenant_id=tenant.tenant_id,
        voter_id=actor.user_id,
        voter_public_id=actor.public_id,
        query=body.query,
        scope=body.scope,
        table_key=body.table_key,
        vote=body.vote,
        note=body.note,
        answer_at=body.answer_at,
    )
    return VoteRecorded.model_validate(
        {
            "votes": outcome.votes,
            "answer_rejected": outcome.answer_rejected,
            "forgotten": outcome.forgotten,
        }
    )
