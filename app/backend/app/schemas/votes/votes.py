"""The vote request and its answer (data-dictionary 006-answer-feedback Requirement 1, 5)."""

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictStr, model_validator

from app.domain.models.answer_vote import (
    VOTE_NOTE_MAX_CHARS,
    VOTE_QUERY_MAX_CHARS,
    VOTE_TABLE_KEY_MAX_CHARS,
)

TallyStatus = Literal["rejected", "approved", "disputed", "doubted", ""]


class VoteIn(BaseModel):
    """One 👍/👎 on a suggested table (``scope=table`` with ``table_key``) or on the whole answer
    (``scope=answer``). Too long values are refused, never cut; unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")

    query: StrictStr
    scope: Literal["table", "answer"]
    table_key: StrictStr | None = None
    vote: Literal["up", "down"]
    note: StrictStr | None = None
    answer_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _shape(self) -> Self:
        self.query = self.query.strip()
        if not 1 <= len(self.query) <= VOTE_QUERY_MAX_CHARS:
            raise ValueError("query")
        if self.scope == "table":
            if not self.table_key or len(self.table_key) > VOTE_TABLE_KEY_MAX_CHARS:
                raise ValueError("table_key")
        elif self.table_key is not None:
            raise ValueError("table_key")
        if self.note is not None:
            self.note = self.note.strip() or None
            if self.note is not None and len(self.note) > VOTE_NOTE_MAX_CHARS:
                raise ValueError("note")
        return self


class Tally(BaseModel):
    """The people who voted 👍 and 👎, the support (−1..1, three decimals), the status and the
    newest three reasons of the counted 👎, without names (Requirement 5, 15)."""

    up: int
    down: int
    support: float
    status: TallyStatus
    reasons: list[str]


class VoteRecorded(BaseModel):
    votes: Tally | None
    answer_rejected: bool
    forgotten: int
