"""The analysis record: one analysis job from acceptance to its end (data-dictionary
008-analysis-records Decision 5).

question-analysis opens the row when it accepts the job, updates it when the job starts and when it
reaches its end; a row in a terminal state never changes again and is only deleted. Deletion is
physical (Decision 13): ``is_deleted`` stays false, the deviation from rules/41 the migrated schema
test checks. The list link is a value, not a foreign key (Decision 14).
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
    QUERY_MAX_CHARS,
    REASON_MAX_CHARS,
    SUMMARY_MAX_CHARS,
)
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id

_STATES = "'queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted'"
_FLOWS = "'analyst', 'reused', 'unavailable', 'cancelled', 'failed', 'interrupted'"
_PHASE_COMMENT = "Milliseconds of the {} phase: the summed duration of its keyed steps."


def _phase(name: str) -> Mapped[int]:
    return mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment=_PHASE_COMMENT.format(name),
    )


class AnalysisRecord(AuditSoftDeleteMixin, Base):
    __tablename__ = "analysis_record"
    __table_args__ = (
        Index(
            "ix_analysis_record_tenant_state_asked",
            "tenant_id",
            "state",
            text("asked_at DESC"),
            text("analysis_record_id DESC"),
        ),
        Index("ix_analysis_record_tenant_asker_asked", "tenant_id", "asked_by", "asked_at"),
        CheckConstraint(f"state IN ({_STATES})", name="state_allowed"),
        CheckConstraint(f"flow IS NULL OR flow IN ({_FLOWS})", name="flow_allowed"),
        CheckConstraint(
            "(state IN ('queued', 'running')) = (flow IS NULL)", name="flow_only_when_finished"
        ),
        CheckConstraint("origin IN ('question', 'list')", name="origin_allowed"),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('VAR', 'KISMEN VAR', 'BULUNAMADI')",
            name="verdict_allowed",
        ),
        CheckConstraint(
            "reused_match IS NULL OR reused_match IN ('same_question', 'same_meaning')",
            name="reused_match_allowed",
        ),
        CheckConstraint(f"char_length(query) BETWEEN 1 AND {QUERY_MAX_CHARS}", name="query_length"),
        CheckConstraint(
            "list_position IS NULL OR list_position >= 1", name="list_position_from_one"
        ),
        CheckConstraint("is_deleted = false", name="deletion_is_physical"),
        {
            "comment": (
                "One analysis job of the data-dictionary context (analysis-records capability): a "
                "single question or one term of a term list, from acceptance to its end, with "
                "its full answer and steps. question-analysis opens and updates it; a row in a "
                "terminal state never changes again. Kept without a time limit and deleted "
                "physically only by a manager; is_deleted stays false (Decision 13). No client "
                "address or host name is kept."
            )
        },
    )

    analysis_record_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36),
        default=new_public_id,
        nullable=False,
        unique=True,
        comment="The analysis job's id (UUID) in every analysis and administration endpoint.",
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    asked_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=False,
        comment="The signed-in user who asked; references app_user.user_id (never deleted).",
    )
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=f"Job state: one of {_STATES}; the last four are terminal.",
    )
    flow: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment=(
            f"Who answered, set at the end: one of {_FLOWS} (Analist, Önceki cevap, Yapılamadı, "
            "Durduruldu, Hata, Yarıda kesildi)."
        ),
    )
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the job was accepted (UTC)."
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the job started running (UTC)."
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When the job ended (UTC)."
    )
    queue_wait_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Milliseconds from acceptance to the start."
    )
    query: Mapped[str] = mapped_column(
        Text, nullable=False, comment=f"The question, whole, at most {QUERY_MAX_CHARS} characters."
    )
    fresh: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="True when a new analysis was asked for (no saved answer)."
    )
    origin: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="'question' (single question) or 'list' (a list term)."
    )
    list_public_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="For a list term: the list's public_id, kept as a value (no foreign key).",
    )
    list_file_name: Mapped[str | None] = mapped_column(
        String(LIST_FILE_NAME_MAX_CHARS),
        nullable=True,
        comment="For a list term: the list file's name.",
    )
    list_position: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="For a list term: its position in the list, from 1."
    )
    model: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        default="",
        server_default=text("''"),
        comment="Chat model that wrote the answer (for 'reused' the saved answer's model).",
    )
    verdict: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="'VAR', 'KISMEN VAR', 'BULUNAMADI' or empty."
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
        comment=f"The answer's summary, its first {SUMMARY_MAX_CHARS} characters.",
    )
    table_keys: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="Suggested tables in the answer's order, at most 10 DB.Schema.Object keys.",
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "The full answer of a completed job (question-analysis Requirement 7 and 18): the "
            "analysis result with each column's dictionary row inside, so the result and the "
            "Excel report are made from it after any later import. Read only by the "
            "question-analysis result and report endpoints."
        ),
    )
    unavailable_reason: Mapped[str] = mapped_column(
        String(REASON_MAX_CHARS),
        nullable=False,
        default="",
        server_default=text("''"),
        comment="For 'unavailable': the reason the user saw; never an address or server text.",
    )
    reused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="For 'reused': when the saved answer was written (UTC).",
    )
    reused_query: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="For 'reused': the question the saved answer was written to."
    )
    reused_match: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="For 'reused': 'same_question' (aynı soru) or 'same_meaning' (aynı anlam).",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(ERROR_CODE_MAX_CHARS),
        nullable=True,
        comment="For 'failed', 'cancelled' and 'interrupted': the fixed error code.",
    )
    error_message: Mapped[str | None] = mapped_column(
        String(ERROR_MESSAGE_MAX_CHARS),
        nullable=True,
        comment="The safe Turkish message of the error code; never an exception text.",
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Milliseconds from acceptance to the end."
    )
    llm_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Model calls: the number of 'llm' steps.",
    )
    prompt_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Input tokens summed over the call summaries.",
    )
    completion_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Output tokens summed over the call summaries.",
    )
    dictionary_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default=text("''"),
        comment="Version of the dictionary the job's engine was built from.",
    )
    phase_queue_ms: Mapped[int] = _phase("queue (Sırada bekleme)")
    phase_saved_answer_lookup_ms: Mapped[int] = _phase("saved_answer_lookup (Önceki cevap araması)")
    phase_model_check_ms: Mapped[int] = _phase("model_check (Model sunucusu kontrolü)")
    phase_rule_hints_ms: Mapped[int] = _phase("rule_hints (Arama, kural motoru)")
    phase_analyst_pick_ms: Mapped[int] = _phase("analyst_pick (keys shortlist, family_search)")
    phase_analyst_write_ms: Mapped[int] = _phase("analyst_write (key analyst_report)")
    steps_truncated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="True when the job had more than 500 steps; the later ones are not kept.",
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment=(
            "Steps in opening order, at most 500: seq (from 0), parent (seq or null), name (120), "
            "kind ('step', 'llm', 'event'), key (null or one of queue, saved_answer_lookup, "
            "model_check, rule_hints, shortlist, family_search, analyst_report), start_ms, ms, "
            "status ('ok', 'warn', 'error'), detail (300); an 'llm' step adds call (the "
            "llm-connection call summary: purpose, integration_public_id, model, started_at, "
            "wait_ms, duration_ms, outcome, http_status, requests, adaptations, repaired, "
            "prompt_tokens, completion_tokens) and the model check adds check (outcome, "
            "http_status, duration_ms, cached). No prompt, reply, address or error body."
        ),
    )
    search_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
        comment=(
            "Turkish-folded question, model, summary, list file name and table keys, written "
            "at the end; the text filter searches it. Never returned by the API."
        ),
    )
