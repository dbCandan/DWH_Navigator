"""Chat calls with their request and response bodies, for the admin screen's LLM log page."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.llm import CHAT_MODEL_MAX_LENGTH
from app.domain.models.mixins import AppendOnlyAuditMixin, new_public_id


class LlmCallLog(AppendOnlyAuditMixin, Base):
    __tablename__ = "llm_call_log"
    __table_args__ = (
        Index("ix_llm_call_log_tenant_started", "tenant_id", "started_at"),
        Index("ix_llm_call_log_started", "started_at"),
        {
            "comment": (
                "Chat calls with their request and response bodies, shown on the admin screen's "
                "LLM log page. Rows are inserted once and removed for good when they pass the "
                "retention period (DWHNAVIGATOR_LLM_CALL_LOG_DAYS); nothing updates them, so "
                "there is no update or soft-delete column. Holds no API key, address or header."
            )
        },
    )

    llm_call_log_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        default=new_public_id,
        comment="Opaque identifier the API exposes.",
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Tenant the call was made for; references tenant.tenant_id.",
    )
    purpose: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=(
            "Who made the call; code reflection app.domain.llm.LlmPurpose: 'analysis', "
            "'connection_test', 'evaluation', 'dictionary_sync'."
        ),
    )
    outcome: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="How the call ended; code reflection app.domain.llm.LlmOutcome.",
    )
    model: Mapped[str] = mapped_column(
        String(CHAT_MODEL_MAX_LENGTH), nullable=False, comment="Chat model the call asked for."
    )
    integration_public_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="Public id of the integration; empty for a test of unsaved form values.",
    )
    analysis_public_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="Public id of the analysis that made the call, if any."
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the call started."
    )
    wait_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Milliseconds spent waiting for a free call slot."
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Milliseconds of the whole call, slot wait included."
    )
    http_status: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="HTTP status of the last request; empty without a response."
    )
    requests: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="HTTP requests sent, adaptations and repair included."
    )
    repaired: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="A repair request followed a reply without a JSON object."
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Prompt tokens the server reported over all requests."
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Completion tokens the server reported over all requests."
    )
    adaptations: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Request features the server refused; app.domain.llm.AdaptedFeature values.",
    )
    exchanges: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        comment=(
            "The HTTP requests of the call in order: request and response body, status, duration "
            "and whether a body was cut at app.domain.llm_call_log.MAX_BODY_CHARS."
        ),
    )
