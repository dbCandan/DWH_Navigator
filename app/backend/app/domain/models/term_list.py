"""Term lists and their terms (data-dictionary 005-list-search Veri ve geçiş, Decision 2, 3, 14).

A list belongs to the user who uploaded it; the newest five per person are kept and an older one is
deleted physically with its terms (``is_deleted`` stays false, the deviation from rules/41 the
migrated schema test checks). At most one list of a tenant runs: a partial unique index over the
``running`` rows. A term row is a dependent row keyed by its list and position (no public_id); it
keeps its answer in full, independent of the dictionary.
"""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.analysis_records import (
    ERROR_CODE_MAX_CHARS,
    ERROR_MESSAGE_MAX_CHARS,
    LIST_FILE_NAME_MAX_CHARS,
)
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id
from app.domain.models.visitor import ADDRESS_MAX_CHARS, HOST_MAX_CHARS

TERM_MAX_CHARS = 500
_STATUSES = "'running', 'completed', 'cancelled', 'interrupted'"
_FLOWS = "'analyst', 'reused', 'unavailable'"


class TermList(AuditSoftDeleteMixin, Base):
    __tablename__ = "term_list"
    __table_args__ = (
        Index(
            "uq_term_list_one_running_per_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        Index("ix_term_list_owner_created", "owner_id", text("created_at DESC")),
        Index("ix_term_list_visitor_created", "owner_visitor_id", text("created_at DESC")),
        CheckConstraint("(owner_id IS NULL) <> (owner_visitor_id IS NULL)", name="one_owner"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_allowed"),
        CheckConstraint("term_count BETWEEN 1 AND 200", name="term_count_range"),
        CheckConstraint(
            "current_position IS NULL OR current_position >= 1", name="current_position_from_one"
        ),
        CheckConstraint("(status = 'running') = (run_started_at IS NOT NULL)", name="run_slice"),
        CheckConstraint("is_deleted = false", name="deletion_is_physical"),
        {
            "comment": (
                "A term list of the data-dictionary context (list-search capability): an "
                "uploaded one-column Excel list whose terms go one by one through the question "
                "analysis. Owned by the uploading account or visitor, the newest five per owner are kept, an older "
                "one is deleted physically with its terms (is_deleted stays false). At most one "
                "running list per tenant. The uploaded file itself is never stored."
            )
        },
    )

    term_list_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36),
        default=new_public_id,
        nullable=False,
        unique=True,
        comment="The list's id (UUID) in every term list endpoint.",
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=True,
        comment=(
            "The account that uploaded the list and alone sees, stops and resumes it. Empty when "
            "a visitor uploaded it; exactly one of owner_id and owner_visitor_id is set."
        ),
    )
    owner_visitor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("visitor.visitor_id", ondelete="RESTRICT"),
        nullable=True,
        comment=(
            "The visitor that uploaded the list and alone sees, stops and resumes it; references "
            "visitor.visitor_id. Empty for an account."
        ),
    )
    client_address: Mapped[str | None] = mapped_column(
        String(ADDRESS_MAX_CHARS),
        nullable=True,
        comment=(
            "The visitor's client IP address when it uploaded the list; empty for an account "
            "(personal data, kept and deleted with the row)."
        ),
    )
    client_host: Mapped[str | None] = mapped_column(
        String(HOST_MAX_CHARS),
        nullable=True,
        comment=(
            "The host name the reverse DNS lookup of client_address returned when "
            "it uploaded the list; empty when none or for an account (personal data)."
        ),
    )
    file_name: Mapped[str] = mapped_column(
        String(LIST_FILE_NAME_MAX_CHARS),
        nullable=False,
        comment="The uploaded file's name without folders and control characters.",
    )
    header: Mapped[str] = mapped_column(
        Text, nullable=False, comment="The list's first row, always the header and never searched."
    )
    notes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="The reading notes in order (header, blank rows, repeats, other sheets).",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=(
            f"One of {_STATUSES}: sürüyor, tamamlandı, durduruldu, yarıda kesildi (the process "
            "closed or died while it ran)."
        ),
    )
    stop_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="The owner asked to stop the list; cleared when the list is resumed.",
    )
    current_position: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Position of the term being answered while the list runs."
    )
    term_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Number of terms (1 to 200)."
    )
    dictionary_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="The dictionary version served when the list started (the report's source).",
    )
    run_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Start of the current running slice (UTC); empty while the list does not run.",
    )
    elapsed_before_ms: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Milliseconds of the earlier running slices; pauses are not counted.",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the list last stopped running (UTC); empty while it runs.",
    )


class TermListItem(Base):
    __tablename__ = "term_list_item"
    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 200", name="position_range"),
        CheckConstraint(f"flow IS NULL OR flow IN ({_FLOWS})", name="flow_allowed"),
        CheckConstraint("(answer IS NULL) = (flow IS NULL)", name="flow_with_answer"),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('VAR', 'KISMEN VAR', 'BULUNAMADI')",
            name="verdict_allowed",
        ),
        CheckConstraint("answer IS NULL OR error_code IS NULL", name="answer_or_error"),
        {
            "comment": (
                "One term of a term list (list-search capability), keyed by its list and its "
                "position in the file; a dependent row without public_id (rules/41). Its answer "
                "is kept in full with each column's dictionary row inside, so the term's detail "
                "and the reports open after any later dictionary import. Deleted with its list."
            )
        },
    )

    term_list_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("term_list.term_list_id", ondelete="CASCADE"),
        primary_key=True,
        comment="The list; references term_list.term_list_id, deleted with it.",
    )
    position: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="The term's position in the list, from 1."
    )
    term: Mapped[str] = mapped_column(
        String(TERM_MAX_CHARS), nullable=False, comment="The term as read from the file."
    )
    answer: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "The full answer: the saved form with each column's dictionary row inside "
            "(question-analysis Requirement 18); empty while the term has no answer."
        ),
    )
    flow: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment=f"How the answer was made: one of {_FLOWS}; empty without an answer.",
    )
    verdict: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="VAR, KISMEN VAR or BULUNAMADI; empty without one."
    )
    error_code: Mapped[str | None] = mapped_column(
        String(ERROR_CODE_MAX_CHARS),
        nullable=True,
        comment="Set when the term's analysis ended with an unexpected error.",
    )
    error_message: Mapped[str | None] = mapped_column(
        String(ERROR_MESSAGE_MAX_CHARS),
        nullable=True,
        comment="The safe Turkish message of the term's error; never an exception text.",
    )
    elapsed_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Milliseconds the term took, from entering the queue to its end.",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the term ended (UTC)."
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
