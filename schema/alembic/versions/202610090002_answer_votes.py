"""Add the votes on answers (answer_vote).

Expand-only: one new append-only table, no existing table changes. A vote row is never
changed or deleted and carries no public_id, update or soft-delete column (Decision 3, 13).
Downgrade drops the table and with it every vote.

Spec: data-dictionary/PRDs/006-answer-feedback (Veri ve geçiş).

Revision ID: 202610090002
Revises: 202610090001
Create Date: 2026-10-09 05:03:18.426744
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610090002"
down_revision: str | None = "202610090001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "answer_vote",
        sa.Column("answer_vote_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "voter_id",
            sa.BigInteger(),
            nullable=False,
            comment="The signed-in user who voted; references app_user.user_id (never deleted).",
        ),
        sa.Column(
            "query_text",
            sa.String(length=4000),
            nullable=False,
            comment="The question of the answer voted on, in full (at most 4000 characters).",
        ),
        sa.Column(
            "text_key",
            sa.Text(),
            nullable=False,
            comment="The question's Turkish-folded words, single-spaced (as saved answers key it).",
        ),
        sa.Column(
            "meaning_key",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="The question's concept set under the term dictionary of the vote; may be empty.",
        ),
        sa.Column(
            "scope",
            sa.String(length=8),
            nullable=False,
            comment="What the vote judges: 'table' (one suggested table) or 'answer' (the whole answer).",
        ),
        sa.Column(
            "table_key",
            sa.String(length=300),
            nullable=True,
            comment="The voted table's key (DB.Schema.Object) for a table vote; empty for an answer.",
        ),
        sa.Column(
            "vote",
            sa.String(length=4),
            nullable=False,
            comment="'up' (👍, useful) or 'down' (👎, not suitable).",
        ),
        sa.Column(
            "note",
            sa.String(length=300),
            nullable=True,
            comment="The optional reason of a vote (at most 300 characters), shown without a name.",
        ),
        sa.Column(
            "dictionary_version",
            sa.String(length=64),
            nullable=False,
            comment="The dictionary version served when the vote was cast; another version weighs 0.5.",
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
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "(scope = 'table') = (table_key IS NOT NULL)",
            name=op.f("ck_answer_vote_table_key_only_for_tables"),
        ),
        sa.CheckConstraint(
            "scope IN ('table', 'answer')", name=op.f("ck_answer_vote_scope_allowed")
        ),
        sa.CheckConstraint("vote IN ('up', 'down')", name=op.f("ck_answer_vote_vote_allowed")),
        sa.CheckConstraint(
            "char_length(query_text) BETWEEN 1 AND 4000", name=op.f("ck_answer_vote_query_length")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_answer_vote_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["voter_id"],
            ["app_user.user_id"],
            name=op.f("fk_answer_vote_voter_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("answer_vote_id", name=op.f("pk_answer_vote")),
        comment="One 👍/👎 on a suggested table or on a whole answer (data-dictionary context, answer-feedback capability, source ADR-036). Append-only: a person's last vote per table and per answer counts, rows are never changed or deleted and are kept without a time limit (Decision 3, 13). created_at is the vote's time (UTC).",
    )
    op.create_index(
        "ix_answer_vote_tenant_meaning_key",
        "answer_vote",
        ["tenant_id", "meaning_key"],
        unique=False,
        postgresql_where=sa.text("meaning_key <> ''"),
    )
    op.create_index(
        "ix_answer_vote_tenant_text_key", "answer_vote", ["tenant_id", "text_key"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_answer_vote_tenant_text_key", table_name="answer_vote")
    op.drop_index(
        "ix_answer_vote_tenant_meaning_key",
        table_name="answer_vote",
        postgresql_where=sa.text("meaning_key <> ''"),
    )
    op.drop_table("answer_vote")
