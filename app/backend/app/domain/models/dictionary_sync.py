"""The warehouse dictionary connection, sync runs and their reports (011-dictionary-sync)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id


def _public_id() -> Mapped[str]:
    return mapped_column(Text, default=new_public_id, nullable=False, unique=True)


class DictionarySource(AuditSoftDeleteMixin, Base):
    __tablename__ = "dictionary_source"
    __table_args__ = (
        {"comment": "The SQL Server connection of the warehouse dictionary, one per tenant."},
    )

    dictionary_source_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = _public_id()
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.tenant_id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class DictionarySyncRun(AuditSoftDeleteMixin, Base):
    __tablename__ = "dictionary_sync_run"
    __table_args__ = (
        Index(
            "uq_dictionary_sync_run_one_running",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        CheckConstraint("kind IN ('guncelleme', 'geri_donus')", name="kind_allowed"),
        CheckConstraint(
            "status IN ('running', 'completed', 'no_change', 'pending_approval', 'rejected', "
            "'failed', 'interrupted')",
            name="status_allowed",
        ),
        {"comment": "One dictionary update or rollback and the head of its report."},
    )

    dictionary_sync_run_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = _public_id()
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.tenant_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    progress_done: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    progress_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    new_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    dictionary_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("dictionary_version.dictionary_version_id", ondelete="RESTRICT"),
        nullable=True,
    )
    model: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default="")
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    warnings: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'::text[]")
    )
    error_code: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")


class DictionarySyncChange(Base):
    __tablename__ = "dictionary_sync_change"
    __table_args__ = (
        Index("ix_dictionary_sync_change_kind", "dictionary_sync_run_id", "kind"),
        {"comment": "One line of a dictionary update report."},
    )

    dictionary_sync_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dictionary_sync_run.dictionary_sync_run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    table_key: Mapped[str] = mapped_column(Text, nullable=False)
    column_name: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    field: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    old_value: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    new_value: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default="")


class DictionarySyncSuggestion(Base):
    __tablename__ = "dictionary_sync_suggestion"
    __table_args__ = (
        CheckConstraint("kind IN ('term', 'stopword')", name="kind_allowed"),
        CheckConstraint("status IN ('pending', 'applied')", name="status_allowed"),
        {"comment": "A term or stopword the model proposed; nothing applies without the admin."},
    )

    dictionary_sync_suggestion_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    public_id: Mapped[str] = _public_id()
    dictionary_sync_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dictionary_sync_run.dictionary_sync_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    equivalents: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'::text[]")
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )


class DictionaryTrailDigest(Base):
    __tablename__ = "dictionary_trail_digest"
    __table_args__ = (
        {
            "comment": (
                "Each dictionary column's code trail digest at the last update, kept apart from the "
                "versions so a run that writes no version still remembers it (011-dictionary-sync)."
            )
        },
    )

    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="CASCADE"),
        primary_key=True,
        comment="Tenant whose dictionary the digest belongs to; references tenant.tenant_id.",
    )
    table_key: Mapped[str] = mapped_column(
        Text, primary_key=True, comment="Folded DB.Schema.Object key."
    )
    column_name: Mapped[str] = mapped_column(Text, primary_key=True, comment="Folded column name.")
    digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Digest of the column's lineage steps and its object's filters; no code text.",
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
