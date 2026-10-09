"""Add the term lists (term_list) and their terms (term_list_item).

Expand-only: two new tables, no existing table changes. A list carries the mandatory block
with physical deletion (is_deleted always false) and at most one running row per tenant; a
term is a dependent row deleted with its list. Downgrade drops both tables and every kept
list; the terms' analysis records stay.

Spec: data-dictionary/PRDs/005-list-search (Veri ve geçiş).

Revision ID: 202610090003
Revises: 202610090002
Create Date: 2026-10-09 05:03:18.426744
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610090003"
down_revision: str | None = "202610090002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "term_list",
        sa.Column("term_list_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "public_id",
            sa.String(length=36),
            nullable=False,
            comment="The list's id (UUID) in every term list endpoint.",
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            nullable=False,
            comment="The user who uploaded the list and alone sees, stops and resumes it.",
        ),
        sa.Column(
            "file_name",
            sa.String(length=255),
            nullable=False,
            comment="The uploaded file's name without folders and control characters.",
        ),
        sa.Column(
            "header",
            sa.Text(),
            nullable=False,
            comment="The list's first row, always the header and never searched.",
        ),
        sa.Column(
            "notes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="The reading notes in order (header, blank rows, repeats, other sheets).",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="One of 'running', 'completed', 'cancelled', 'interrupted': sürüyor, tamamlandı, durduruldu, yarıda kesildi (the process closed or died while it ran).",
        ),
        sa.Column(
            "stop_requested",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="The owner asked to stop the list; cleared when the list is resumed.",
        ),
        sa.Column(
            "current_position",
            sa.Integer(),
            nullable=True,
            comment="Position of the term being answered while the list runs.",
        ),
        sa.Column(
            "term_count", sa.Integer(), nullable=False, comment="Number of terms (1 to 200)."
        ),
        sa.Column(
            "dictionary_version",
            sa.String(length=64),
            nullable=False,
            comment="The dictionary version served when the list started (the report's source).",
        ),
        sa.Column(
            "run_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Start of the current running slice (UTC); empty while the list does not run.",
        ),
        sa.Column(
            "elapsed_before_ms",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Milliseconds of the earlier running slices; pauses are not counted.",
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the list last stopped running (UTC); empty while it runs.",
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
            "(status = 'running') = (run_started_at IS NOT NULL)",
            name=op.f("ck_term_list_run_slice"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'cancelled', 'interrupted')",
            name=op.f("ck_term_list_status_allowed"),
        ),
        sa.CheckConstraint(
            "current_position IS NULL OR current_position >= 1",
            name=op.f("ck_term_list_current_position_from_one"),
        ),
        sa.CheckConstraint("is_deleted = false", name=op.f("ck_term_list_deletion_is_physical")),
        sa.CheckConstraint(
            "term_count BETWEEN 1 AND 200", name=op.f("ck_term_list_term_count_range")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["app_user.user_id"],
            name=op.f("fk_term_list_owner_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_term_list_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("term_list_id", name=op.f("pk_term_list")),
        sa.UniqueConstraint("public_id", name=op.f("uq_term_list_public_id")),
        comment="A term list of the data-dictionary context (list-search capability): an uploaded one-column Excel list whose terms go one by one through the question analysis. Owned by the uploader, the newest five per person are kept, an older one is deleted physically with its terms (is_deleted stays false). At most one running list per tenant. The uploaded file itself is never stored.",
    )
    op.create_index(
        "ix_term_list_owner_created",
        "term_list",
        ["owner_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_term_list_one_running_per_tenant",
        "term_list",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "term_list_item",
        sa.Column(
            "term_list_id",
            sa.BigInteger(),
            nullable=False,
            comment="The list; references term_list.term_list_id, deleted with it.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="The term's position in the list, from 1.",
        ),
        sa.Column(
            "term", sa.String(length=500), nullable=False, comment="The term as read from the file."
        ),
        sa.Column(
            "answer",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="The full answer: the saved form with each column's dictionary row inside (question-analysis Requirement 18); empty while the term has no answer.",
        ),
        sa.Column(
            "flow",
            sa.String(length=16),
            nullable=True,
            comment="How the answer was made: one of 'analyst', 'reused', 'unavailable'; empty without an answer.",
        ),
        sa.Column(
            "verdict",
            sa.String(length=16),
            nullable=True,
            comment="VAR, KISMEN VAR or BULUNAMADI; empty without one.",
        ),
        sa.Column(
            "error_code",
            sa.String(length=64),
            nullable=True,
            comment="Set when the term's analysis ended with an unexpected error.",
        ),
        sa.Column(
            "error_message",
            sa.String(length=500),
            nullable=True,
            comment="The safe Turkish message of the term's error; never an exception text.",
        ),
        sa.Column(
            "elapsed_ms",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Milliseconds the term took, from entering the queue to its end.",
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the term ended (UTC).",
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
        sa.CheckConstraint(
            "flow IS NULL OR flow IN ('analyst', 'reused', 'unavailable')",
            name=op.f("ck_term_list_item_flow_allowed"),
        ),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('VAR', 'KISMEN VAR', 'BULUNAMADI')",
            name=op.f("ck_term_list_item_verdict_allowed"),
        ),
        sa.CheckConstraint(
            "(answer IS NULL) = (flow IS NULL)", name=op.f("ck_term_list_item_flow_with_answer")
        ),
        sa.CheckConstraint(
            "answer IS NULL OR error_code IS NULL", name=op.f("ck_term_list_item_answer_or_error")
        ),
        sa.CheckConstraint(
            "position BETWEEN 1 AND 200", name=op.f("ck_term_list_item_position_range")
        ),
        sa.ForeignKeyConstraint(
            ["term_list_id"],
            ["term_list.term_list_id"],
            name=op.f("fk_term_list_item_term_list_id_term_list"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("term_list_id", "position", name=op.f("pk_term_list_item")),
        comment="One term of a term list (list-search capability), keyed by its list and its position in the file; a dependent row without public_id (rules/41). Its answer is kept in full with each column's dictionary row inside, so the term's detail and the reports open after any later dictionary import. Deleted with its list.",
    )


def downgrade() -> None:
    op.drop_table("term_list_item")
    op.drop_index(
        "uq_term_list_one_running_per_tenant",
        table_name="term_list",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index("ix_term_list_owner_created", table_name="term_list")
    op.drop_table("term_list")
