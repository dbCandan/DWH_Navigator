"""Saved answers (data-dictionary 004-question-analysis Decision 3 and 9).

A saved answer is a cache, not a record: the same or the same-meaning question gets it back while
the fingerprint matches. Rows are deleted physically and the table carries no soft-delete columns
(Decision 9, the documented deviation from rules/41). The answer's lasting record is the analysis
record; the link to it empties when that record is deleted.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.analysis_records import SAVED_QUERY_MAX_CHARS
from app.domain.models.mixins import new_public_id


class SavedAnswer(Base):
    __tablename__ = "saved_answer"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "text_key", "fingerprint", name="uq_saved_answer_tenant_text_fingerprint"
        ),
        Index(
            "ix_saved_answer_tenant_fingerprint_answered",
            "tenant_id",
            "fingerprint",
            text("answered_at DESC"),
        ),
        Index(
            "ix_saved_answer_tenant_meaning_fingerprint_answered",
            "tenant_id",
            "meaning_key",
            "fingerprint",
            text("answered_at DESC"),
        ),
        {
            "comment": (
                "An analyst answer kept for the same or a same-meaning question (data-dictionary "
                "context, question-analysis capability, source ADR-035). Shared by the tenant's "
                "users; used only while the fingerprint matches; the newest 2000 are kept and "
                "rows are deleted physically (no soft-delete columns, Decision 9). created_by is "
                "the user whose question produced the answer."
            )
        },
    )

    saved_answer_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), default=new_public_id, nullable=False, unique=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    query_text: Mapped[str] = mapped_column(
        String(SAVED_QUERY_MAX_CHARS),
        nullable=False,
        comment="The question the answer was written to, its first 2000 characters.",
    )
    text_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The question's Turkish-folded words, single-spaced (answer_cache.text_key).",
    )
    meaning_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
        comment="Canonical concept set of the question; empty without a content concept.",
    )
    fingerprint: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=(
            "First 16 hex digits of the SHA-256 of what the answer depends on: format, "
            "dictionary version, word lists, top, prompts, settings and the chat model."
        ),
    )
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment=(
            "The answer in the source's saved form (answer_cache.encode, columns by key), "
            "rebuilt from the current dictionary when given again."
        ),
    )
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the answer was written (UTC)."
    )
    analysis_public_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("analysis_record.public_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="The analysis record that produced the answer; empties when it is deleted.",
    )
    props: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
