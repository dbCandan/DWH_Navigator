"""Add the model server connections (llm_integration).

Expand-only: it adds one table with its constraints and indexes and changes no existing table.
Downgrade drops the table and every saved connection; analyses then end with not_configured until
an administrator enters a connection again.

Spec: data-dictionary/PRDs/003-llm-connection (Veri ve geçiş).

Revision ID: 202610080002
Revises: 202610080001
Create Date: 2026-10-08 18:40:48.852139
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202610080002"
down_revision: str | None = "202610080001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_integration",
        sa.Column("llm_integration_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
            comment="Display name the administrator chose; 1-100 characters, no control character.",
        ),
        sa.Column(
            "name_key",
            sa.String(length=100),
            nullable=False,
            comment="The name with Turkish case and letter folding (app.domain.turkish_text.fold); unique among the tenant's non-deleted integrations.",
        ),
        sa.Column(
            "endpoint",
            sa.String(length=2048),
            nullable=False,
            comment="Normalized base address of the OpenAI-compatible API (the /v1 address): trimmed, without a trailing '/', '/chat/completions' or '/models'; at most 2048 characters. The scheme, host and port form the origin the stored key belongs to.",
        ),
        sa.Column(
            "api_key_ciphertext",
            sa.Text(),
            nullable=True,
            comment="API key sealed with AES-256-GCM as 'v1.<nonce>.<ciphertext>'; the key is the settings encryption key of the runtime Secret and the value is bound to the tenant, this row's public_id and the endpoint origin. Empty when the server needs no key and after deletion. The plain key is never stored.",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True for the tenant's single active chat model (partial unique index over non-deleted rows); an active row has a chat model and is never deleted.",
        ),
        sa.Column(
            "chat_model",
            sa.String(length=256),
            server_default=sa.text("''"),
            nullable=False,
            comment="Model id sent as 'model' in chat requests; empty until one is chosen.",
        ),
        sa.Column(
            "temperature",
            sa.Double(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Sampling temperature sent with every chat request, 0 to 2.",
        ),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            server_default=sa.text("900"),
            nullable=False,
            comment="Longest wait for each send and read of a chat request, 5 to 3600 seconds.",
        ),
        sa.Column(
            "reasoning_effort",
            sa.String(length=8),
            server_default=sa.text("'none'"),
            nullable=False,
            comment="Thinking mode sent as 'reasoning_effort'; code reflection app.domain.llm.REASONING_EFFORTS: 'none', 'low', 'medium', 'high', or '' = the field is not sent.",
        ),
        sa.Column(
            "seed",
            sa.Integer(),
            server_default=sa.text("42"),
            nullable=False,
            comment="Seed sent with every chat request; -1 = the field is not sent.",
        ),
        sa.Column(
            "last_test_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time of the last recorded connection test; emptied when the endpoint or the chat model changes. Set together with last_test_ok and last_test_summary.",
        ),
        sa.Column(
            "last_test_ok",
            sa.Boolean(),
            nullable=True,
            comment="Whether every step of the last recorded test passed.",
        ),
        sa.Column(
            "last_test_summary",
            sa.String(length=200),
            nullable=True,
            comment="Steps of the last recorded test, e.g. 'Sunucu: ✓; Sohbet modeli: ✓'.",
        ),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "NOT active OR chat_model <> ''",
            name=op.f("ck_llm_integration_active_needs_chat_model"),
        ),
        sa.CheckConstraint(
            "reasoning_effort IN ('none', 'low', 'medium', 'high', '')",
            name=op.f("ck_llm_integration_reasoning_effort_allowed"),
        ),
        sa.CheckConstraint(
            "(last_test_at IS NULL) = (last_test_ok IS NULL) AND (last_test_at IS NULL) = (last_test_summary IS NULL)",
            name=op.f("ck_llm_integration_last_test_complete"),
        ),
        sa.CheckConstraint(
            "NOT (active AND is_deleted)", name=op.f("ck_llm_integration_deleted_is_inactive")
        ),
        sa.CheckConstraint(
            "NOT is_deleted OR api_key_ciphertext IS NULL",
            name=op.f("ck_llm_integration_deleted_has_no_key"),
        ),
        sa.CheckConstraint(
            "char_length(chat_model) <= 256", name=op.f("ck_llm_integration_chat_model_length")
        ),
        sa.CheckConstraint(
            "char_length(endpoint) BETWEEN 1 AND 2048",
            name=op.f("ck_llm_integration_endpoint_length"),
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 100", name=op.f("ck_llm_integration_name_length")
        ),
        sa.CheckConstraint(
            "seed BETWEEN -1 AND 2147483647", name=op.f("ck_llm_integration_seed_range")
        ),
        sa.CheckConstraint(
            "temperature BETWEEN 0 AND 2", name=op.f("ck_llm_integration_temperature_range")
        ),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 5 AND 3600",
            name=op.f("ck_llm_integration_timeout_seconds_range"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_llm_integration_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("llm_integration_id", name=op.f("pk_llm_integration")),
        sa.UniqueConstraint("public_id", name=op.f("uq_llm_integration_public_id")),
        comment="Model server connection (integration) of the data-dictionary context's llm-connection capability: an OpenAI-compatible in-house server that may hold the single chat-model role. The administrator adds, edits, activates and deletes rows from the AI page; deletion is soft and empties the stored key. Every analysis reads the active row once before its model steps. updated_at and updated_by are the last connection change and the user who made it; a recorded test result changes neither.",
    )
    op.create_index(
        "ix_llm_integration_active_public_id",
        "llm_integration",
        ["public_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        op.f("ix_llm_integration_tenant_id"), "llm_integration", ["tenant_id"], unique=False
    )
    op.create_index(
        "uq_llm_integration_tenant_active",
        "llm_integration",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("active AND is_deleted = false"),
    )
    op.create_index(
        "uq_llm_integration_tenant_name_key",
        "llm_integration",
        ["tenant_id", "name_key"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_llm_integration_tenant_name_key",
        table_name="llm_integration",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_index(
        "uq_llm_integration_tenant_active",
        table_name="llm_integration",
        postgresql_where=sa.text("active AND is_deleted = false"),
    )
    op.drop_index(op.f("ix_llm_integration_tenant_id"), table_name="llm_integration")
    op.drop_index(
        "ix_llm_integration_active_public_id",
        table_name="llm_integration",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("llm_integration")
