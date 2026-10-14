"""Votes on answers (data-dictionary 006-answer-feedback Veri ve geçiş, Decision 3 and 13).

An append-only stream: every 👍/👎 is a new row, a person's last row per table and per answer is
chosen when the votes are read, and rows are neither changed nor deleted (kept without a time
limit). It carries no public_id and no update or soft-delete column, the deviation from rules/41
the PRD states and the migrated schema test checks. ``created_at`` is the vote's time.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AppendOnlyAuditMixin
from app.domain.models.visitor import ADDRESS_MAX_CHARS, HOST_MAX_CHARS

VOTE_QUERY_MAX_CHARS = 4000
VOTE_TABLE_KEY_MAX_CHARS = 300
VOTE_NOTE_MAX_CHARS = 300


class AnswerVote(AppendOnlyAuditMixin, Base):
    __tablename__ = "answer_vote"
    __table_args__ = (
        Index("ix_answer_vote_tenant_text_key", "tenant_id", "text_key"),
        Index(
            "ix_answer_vote_tenant_meaning_key",
            "tenant_id",
            "meaning_key",
            postgresql_where=text("meaning_key <> ''"),
        ),
        Index("ix_answer_vote_voter_visitor", "voter_visitor_id"),
        CheckConstraint("(voter_id IS NULL) <> (voter_visitor_id IS NULL)", name="one_voter"),
        CheckConstraint("scope IN ('table', 'answer')", name="scope_allowed"),
        CheckConstraint("vote IN ('up', 'down')", name="vote_allowed"),
        CheckConstraint(
            "(scope = 'table') = (table_key IS NOT NULL)", name="table_key_only_for_tables"
        ),
        CheckConstraint(
            f"char_length(query_text) BETWEEN 1 AND {VOTE_QUERY_MAX_CHARS}", name="query_length"
        ),
        {
            "comment": (
                "One 👍/👎 on a suggested table or on a whole answer (data-dictionary context, "
                "answer-feedback capability, source ADR-036). Append-only: a person's last vote "
                "per table and per answer counts, rows are never changed or deleted and are kept "
                "without a time limit (Decision 3, 13). created_at is the vote's time (UTC)."
            )
        },
    )

    answer_vote_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    voter_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=True,
        comment=(
            "The account that voted; references app_user.user_id (never deleted). Empty when a "
            "visitor voted; exactly one of voter_id and voter_visitor_id is set."
        ),
    )
    voter_visitor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("visitor.visitor_id", ondelete="RESTRICT"),
        nullable=True,
        comment="The visitor that voted; references visitor.visitor_id. Empty for an account.",
    )
    client_address: Mapped[str | None] = mapped_column(
        String(ADDRESS_MAX_CHARS),
        nullable=True,
        comment=(
            "The visitor's client IP address when it voted; empty for an account "
            "(personal data, kept and deleted with the row)."
        ),
    )
    client_host: Mapped[str | None] = mapped_column(
        String(HOST_MAX_CHARS),
        nullable=True,
        comment=(
            "The host name the reverse DNS lookup of client_address returned when "
            "it voted; empty when none or for an account (personal data)."
        ),
    )
    query_text: Mapped[str] = mapped_column(
        String(VOTE_QUERY_MAX_CHARS),
        nullable=False,
        comment="The question of the answer voted on, in full (at most 4000 characters).",
    )
    text_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The question's Turkish-folded words, single-spaced (as saved answers key it).",
    )
    meaning_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
        comment="The question's concept set under the term dictionary of the vote; may be empty.",
    )
    scope: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment="What the vote judges: 'table' (one suggested table) or 'answer' (the whole answer).",
    )
    table_key: Mapped[str | None] = mapped_column(
        String(VOTE_TABLE_KEY_MAX_CHARS),
        nullable=True,
        comment="The voted table's key (DB.Schema.Object) for a table vote; empty for an answer.",
    )
    vote: Mapped[str] = mapped_column(
        String(4), nullable=False, comment="'up' (👍, useful) or 'down' (👎, not suitable)."
    )
    note: Mapped[str | None] = mapped_column(
        String(VOTE_NOTE_MAX_CHARS),
        nullable=True,
        comment="The optional reason of a vote (at most 300 characters), shown without a name.",
    )
    dictionary_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="The dictionary version served when the vote was cast; another version weighs 0.5.",
    )
