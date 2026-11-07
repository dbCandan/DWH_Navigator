"""LLM call log: chat calls with their request and response bodies.

Revision ID: 202611070002
Revises: 202611070001
Create Date: 2026-11-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202611070002"
down_revision: str | None = "202611070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_call_log",
        sa.Column("llm_call_log_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False, comment="Opaque identifier the API exposes."),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            sa.ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
            nullable=False,
            comment="Tenant the call was made for; references tenant.tenant_id.",
        ),
        sa.Column(
            "purpose",
            sa.String(32),
            nullable=False,
            comment=(
                "Who made the call; code reflection app.domain.llm.LlmPurpose: 'analysis', "
                "'connection_test', 'evaluation', 'dictionary_sync'."
            ),
        ),
        sa.Column(
            "outcome",
            sa.String(32),
            nullable=False,
            comment="How the call ended; code reflection app.domain.llm.LlmOutcome.",
        ),
        sa.Column("model", sa.String(256), nullable=False, comment="Chat model the call asked for."),
        sa.Column(
            "integration_public_id",
            sa.String(36),
            nullable=True,
            comment="Public id of the integration; empty for a test of unsaved form values.",
        ),
        sa.Column(
            "analysis_public_id",
            sa.String(36),
            nullable=True,
            comment="Public id of the analysis that made the call, if any.",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, comment="When the call started."),
        sa.Column("wait_ms", sa.Integer(), nullable=False, comment="Milliseconds spent waiting for a free call slot."),
        sa.Column(
            "duration_ms", sa.Integer(), nullable=False, comment="Milliseconds of the whole call, slot wait included."
        ),
        sa.Column(
            "http_status", sa.Integer(), nullable=True, comment="HTTP status of the last request; empty without a response."
        ),
        sa.Column(
            "requests", sa.Integer(), nullable=False, comment="HTTP requests sent, adaptations and repair included."
        ),
        sa.Column(
            "repaired", sa.Boolean(), nullable=False, comment="A repair request followed a reply without a JSON object."
        ),
        sa.Column(
            "prompt_tokens", sa.Integer(), nullable=False, comment="Prompt tokens the server reported over all requests."
        ),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=False,
            comment="Completion tokens the server reported over all requests.",
        ),
        sa.Column(
            "adaptations",
            postgresql.JSONB(),
            nullable=False,
            comment="Request features the server refused; app.domain.llm.AdaptedFeature values.",
        ),
        sa.Column(
            "exchanges",
            postgresql.JSONB(),
            nullable=False,
            comment=(
                "The HTTP requests of the call in order: request and response body, status, duration "
                "and whether a body was cut at app.domain.llm_call_log.MAX_BODY_CHARS."
            ),
        ),
        sa.Column("props", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("public_id"),
        comment=(
            "Chat calls with their request and response bodies, shown on the admin screen's "
            "LLM log page. Rows are inserted once and removed for good when they pass the "
            "retention period (DWHNAVIGATOR_LLM_CALL_LOG_DAYS); nothing updates them, so "
            "there is no update or soft-delete column. Holds no API key, address or header."
        ),
    )
    op.create_index("ix_llm_call_log_tenant_started", "llm_call_log", ["tenant_id", "started_at"])
    op.create_index("ix_llm_call_log_started", "llm_call_log", ["started_at"])


def downgrade() -> None:
    op.drop_table("llm_call_log")
