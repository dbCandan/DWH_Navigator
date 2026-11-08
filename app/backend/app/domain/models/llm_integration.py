"""Model server connection (integration) of a tenant (data-dictionary 003-llm-connection).

The administrator manages the rows from the AI page; the API key is stored only as authenticated
ciphertext whose key lives in the runtime Secret. At most one non-deleted row per tenant is the
active chat model, enforced by a partial unique index; an active row always names a chat model.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.llm import (
    CHAT_MODEL_MAX_LENGTH,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_SEED,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    ENDPOINT_MAX_LENGTH,
    NAME_MAX_LENGTH,
)
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id

INHERIT = "inherit"  # a generation setting that uses the chat model's own


class LlmIntegration(AuditSoftDeleteMixin, Base):
    __tablename__ = "llm_integration"
    __table_args__ = (
        Index(
            "ix_llm_integration_active_public_id",
            "public_id",
            postgresql_where=text("is_deleted = false"),
        ),
        # Requirement 2: a name is unique among a tenant's non-deleted integrations.
        Index(
            "uq_llm_integration_tenant_name_key",
            "tenant_id",
            "name_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        # Requirement 4: at most one active chat model per tenant.
        Index(
            "uq_llm_integration_tenant_active",
            "tenant_id",
            unique=True,
            postgresql_where=text("active AND is_deleted = false"),
        ),
        CheckConstraint(
            f"char_length(name) BETWEEN 1 AND {NAME_MAX_LENGTH}", name="name_length"
        ),
        CheckConstraint(
            f"char_length(endpoint) BETWEEN 1 AND {ENDPOINT_MAX_LENGTH}",
            name="endpoint_length",
        ),
        CheckConstraint(
            f"char_length(chat_model) <= {CHAT_MODEL_MAX_LENGTH}",
            name="chat_model_length",
        ),
        CheckConstraint(
            "NOT active OR chat_model <> ''", name="active_needs_chat_model"
        ),
        CheckConstraint("NOT (active AND is_deleted)", name="deleted_is_inactive"),
        CheckConstraint(
            "NOT is_deleted OR api_key_ciphertext IS NULL", name="deleted_has_no_key"
        ),
        CheckConstraint("temperature BETWEEN 0 AND 2", name="temperature_range"),
        CheckConstraint(
            "timeout_seconds BETWEEN 5 AND 3600", name="timeout_seconds_range"
        ),
        CheckConstraint(
            "reasoning_effort IN ('none', 'low', 'medium', 'high', '')",
            name="reasoning_effort_allowed",
        ),
        CheckConstraint("seed BETWEEN -1 AND 2147483647", name="seed_range"),
        CheckConstraint(
            f"char_length(generation_model) <= {CHAT_MODEL_MAX_LENGTH}",
            name="generation_model_length",
        ),
        CheckConstraint(
            "generation_reasoning_effort IN ('inherit', 'none', 'low', 'medium', 'high', '')",
            name="generation_reasoning_effort_allowed",
        ),
        CheckConstraint(
            "judge_reasoning_effort IN ('inherit', 'none', 'low', 'medium', 'high', '')",
            name="judge_reasoning_effort_allowed",
        ),
        CheckConstraint(
            "(last_test_at IS NULL) = (last_test_ok IS NULL) "
            "AND (last_test_at IS NULL) = (last_test_summary IS NULL)",
            name="last_test_complete",
        ),
        {
            "comment": (
                "Model server connection (integration) of the data-dictionary context's "
                "llm-connection capability: an OpenAI-compatible in-house server that may hold the "
                "single chat-model role. The administrator adds, edits, activates and deletes rows "
                "from the AI page; deletion is soft and empties the stored key. Every analysis reads "
                "the active row once before its model steps. updated_at and updated_by are the "
                "last connection change and the user who made it; a recorded test result changes "
                "neither."
            )
        },
    )

    llm_integration_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    public_id: Mapped[str] = mapped_column(
        Text,
        default=new_public_id,
        nullable=False,
        unique=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    name: Mapped[str] = mapped_column(
        String(NAME_MAX_LENGTH),
        nullable=False,
        comment="Display name the administrator chose; 1-100 characters, no control character.",
    )
    name_key: Mapped[str] = mapped_column(
        String(NAME_MAX_LENGTH),
        nullable=False,
        comment=(
            "The name with Turkish case and letter folding (app.domain.turkish_text.fold); unique "
            "among the tenant's non-deleted integrations."
        ),
    )
    endpoint: Mapped[str] = mapped_column(
        String(ENDPOINT_MAX_LENGTH),
        nullable=False,
        comment=(
            "Normalized base address of the OpenAI-compatible API (the /v1 address): trimmed, "
            "without a trailing '/', '/chat/completions' or '/models'; at most 2048 characters. "
            "The scheme, host and port form the origin the stored key belongs to."
        ),
    )
    api_key_ciphertext: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "API key sealed with AES-256-GCM as 'v1.<nonce>.<ciphertext>'; the key is the "
            "settings encryption key of the runtime Secret and the value is bound to the tenant, "
            "this row's public_id and the endpoint origin. Empty when the server needs no key "
            "and after deletion. The plain key is never stored."
        ),
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment=(
            "True for the tenant's single active chat model (partial unique index over non-"
            "deleted rows); an active row has a chat model and is never deleted."
        ),
    )
    chat_model: Mapped[str] = mapped_column(
        String(CHAT_MODEL_MAX_LENGTH),
        nullable=False,
        default="",
        server_default=text("''"),
        comment="Model id sent as 'model' in chat requests; empty until one is chosen.",
    )
    temperature: Mapped[float] = mapped_column(
        Double,
        nullable=False,
        default=DEFAULT_TEMPERATURE,
        server_default=text("0"),
        comment="Sampling temperature sent with every chat request, 0 to 2.",
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_TIMEOUT_SECONDS,
        server_default=text("900"),
        comment="Longest wait for each send and read of a chat request, 5 to 3600 seconds.",
    )
    reasoning_effort: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=DEFAULT_REASONING_EFFORT,
        server_default=text("'none'"),
        comment=(
            "Thinking mode sent as 'reasoning_effort'; code reflection app.domain.llm."
            "REASONING_EFFORTS: 'none', 'low', 'medium', 'high', or '' = the field is not sent."
        ),
    )
    generation_model: Mapped[str] = mapped_column(
        String(CHAT_MODEL_MAX_LENGTH),
        nullable=False,
        default="",
        server_default="",
        comment="The generation model: the dictionary update describes with it; empty uses chat_model.",
    )
    generation_reasoning_effort: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=INHERIT,
        server_default=INHERIT,
        comment="Reasoning of the generation model's describing calls; 'inherit' uses reasoning_effort.",
    )
    judge_reasoning_effort: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=INHERIT,
        server_default=INHERIT,
        comment="Reasoning of the dictionary update's verifier calls; 'inherit' uses reasoning_effort.",
    )
    seed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_SEED,
        server_default=text("42"),
        comment="Seed sent with every chat request; -1 = the field is not sent.",
    )
    last_test_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "UTC time of the last recorded connection test; emptied when the endpoint or the "
            "chat model changes. Set together with last_test_ok and last_test_summary."
        ),
    )
    last_test_ok: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="Whether every step of the last recorded test passed.",
    )
    last_test_summary: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Steps of the last recorded test, e.g. 'Sunucu: ✓; Sohbet modeli: ✓'.",
    )
