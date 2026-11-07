"""Dictionary sync: source connection, sync runs, reports, kept versions.

Versions are kept for a month, so more than one 'previous' version may exist and a version may wait
for approval ('pending'). superseded_at is the start of the retention period.

Spec: data-dictionary/PRDs/011-dictionary-sync.

Revision ID: 202611070001
Revises: 202611040001
Create Date: 2026-11-07 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202611070001"
down_revision: str | None = "202611040001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit() -> list[sa.Column]:
    return [
        sa.Column("props", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
    ]


def upgrade() -> None:
    op.drop_index(
        "uq_dictionary_version_tenant_previous",
        table_name="dictionary_version",
        postgresql_where=sa.text("status = 'previous' AND is_deleted = false"),
    )
    op.drop_constraint("status_allowed", "dictionary_version", type_="check")
    op.drop_constraint("channel_allowed", "dictionary_version", type_="check")
    op.alter_column(
        "dictionary_version",
        "channel",
        type_=sa.String(16),
        existing_type=sa.String(8),
        comment=(
            "Code reflection app.domain.dictionary.ImportChannel: 'arayuz' = admin screen, "
            "'betik' = backend script, 'kaynak' = warehouse sync, 'geri_donus' = rollback."
        ),
    )
    op.create_check_constraint(
        "status_allowed",
        "dictionary_version",
        "status IN ('active', 'previous', 'pending', 'pruned')",
    )
    op.create_check_constraint(
        "channel_allowed",
        "dictionary_version",
        "channel IN ('arayuz', 'betik', 'kaynak', 'geri_donus')",
    )
    op.add_column(
        "dictionary_version",
        sa.Column(
            "superseded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this version stopped being active; the 30 day retention starts here.",
        ),
    )
    op.execute(
        "UPDATE dictionary_version SET superseded_at = updated_at WHERE status = 'previous'"
    )

    op.create_table(
        "dictionary_source",
        sa.Column("dictionary_source_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            sa.ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database_name", sa.String(128), nullable=False),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("password_ciphertext", sa.Text(), nullable=True),
        sa.Column("encrypt", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_audit(),
        comment="The SQL Server connection of the warehouse dictionary, one per tenant.",
    )

    op.create_table(
        "dictionary_sync_run",
        sa.Column("dictionary_sync_run_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            sa.ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("progress_done", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("new_version", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "dictionary_version_id",
            sa.BigInteger(),
            sa.ForeignKey("dictionary_version.dictionary_version_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("model", sa.String(256), nullable=False, server_default=""),
        sa.Column("counts", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "warnings",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("error_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        *_audit(),
        sa.CheckConstraint("kind IN ('guncelleme', 'geri_donus')", name="kind_allowed"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'no_change', 'pending_approval', 'rejected', "
            "'failed', 'interrupted')",
            name="status_allowed",
        ),
        comment="One dictionary update or rollback and the head of its report.",
    )
    op.create_index(
        "uq_dictionary_sync_run_one_running",
        "dictionary_sync_run",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.create_table(
        "dictionary_sync_change",
        sa.Column(
            "dictionary_sync_run_id",
            sa.BigInteger(),
            sa.ForeignKey("dictionary_sync_run.dictionary_sync_run_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("table_key", sa.Text(), nullable=False),
        sa.Column("column_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("field", sa.String(64), nullable=False, server_default=""),
        sa.Column("old_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("new_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("origin", sa.String(16), nullable=False, server_default=""),
        comment="One line of a dictionary update report.",
    )
    op.create_index(
        "ix_dictionary_sync_change_kind",
        "dictionary_sync_change",
        ["dictionary_sync_run_id", "kind"],
    )

    op.create_table(
        "dictionary_sync_suggestion",
        sa.Column("dictionary_sync_suggestion_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "dictionary_sync_run_id",
            sa.BigInteger(),
            sa.ForeignKey("dictionary_sync_run.dictionary_sync_run_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "equivalents",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.CheckConstraint("kind IN ('term', 'stopword')", name="kind_allowed"),
        sa.CheckConstraint("status IN ('pending', 'applied')", name="status_allowed"),
        comment="A term or stopword the model proposed; nothing applies without the admin.",
    )


def downgrade() -> None:
    op.drop_table("dictionary_sync_suggestion")
    op.drop_table("dictionary_sync_change")
    op.drop_table("dictionary_sync_run")
    op.drop_table("dictionary_source")
    # The old rules allow one previous version and no waiting version: the others are pruned.
    keep = """
        status IN ('previous', 'pending') AND dictionary_version_id NOT IN (
            SELECT max(dictionary_version_id) FROM dictionary_version
            WHERE status = 'previous' GROUP BY tenant_id
        )
    """
    for table in ("dictionary_column_record", "dictionary_object_record"):
        op.execute(
            f"DELETE FROM {table} WHERE dictionary_version_id IN "
            f"(SELECT dictionary_version_id FROM dictionary_version WHERE {keep})"
        )
    op.execute(
        f"UPDATE dictionary_version SET status = 'pruned', is_deleted = true, "
        f"deleted_at = now() WHERE {keep}"
    )
    op.execute("UPDATE dictionary_version SET channel = 'betik' WHERE channel NOT IN ('arayuz', 'betik')")
    op.drop_column("dictionary_version", "superseded_at")
    op.drop_constraint("channel_allowed", "dictionary_version", type_="check")
    op.drop_constraint("status_allowed", "dictionary_version", type_="check")
    op.alter_column(
        "dictionary_version",
        "channel",
        type_=sa.String(8),
        existing_type=sa.String(16),
        comment=(
            "Code reflection app.domain.dictionary.ImportChannel: 'arayuz' = admin screen, "
            "'betik' = backend script."
        ),
    )
    op.create_check_constraint(
        "status_allowed", "dictionary_version", "status IN ('active', 'previous', 'pruned')"
    )
    op.create_check_constraint(
        "channel_allowed", "dictionary_version", "channel IN ('arayuz', 'betik')"
    )
    op.create_index(
        "uq_dictionary_version_tenant_previous",
        "dictionary_version",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'previous' AND is_deleted = false"),
    )
