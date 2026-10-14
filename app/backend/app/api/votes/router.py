"""Vote endpoint (data-dictionary/PRDs/006-answer-feedback, API sözleşmesi).

No session: the voter is the visitor of the ``X-Device-Id`` header (Decision 2,
application-foundation 003-anonymous-visitor). No question, table key or reason reaches a log, a
metric or a trace.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.visitor.dependencies import CurrentVisitor, visitor_asker
from app.schemas.errors import error_responses
from app.schemas.votes.votes import VoteIn, VoteRecorded
from app.services.answer_feedback import AnswerVotes

router = APIRouter(
    tags=["votes"],
    responses=error_responses(
        {
            400: "device_id_required: X-Device-Id eksik ya da UUID 4 değil",
            403: "tenant_forbidden: başka kiracı; cross_site_request: istek başka bir siteden geldi",
            429: "rate_limited: ziyaretçi ya da adres sınırı",
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
    visitor: CurrentVisitor,
    votes: Annotated[AnswerVotes, Depends(get_answer_votes)],
) -> VoteRecorded:
    """Record a 👍/👎; the last vote of each person counts. Enough 👎 on the whole answer delete
    the question's saved answers, so it is analysed anew."""

    outcome = await votes.record(
        tenant_id=visitor.tenant_id,
        voter=visitor_asker(visitor),
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
