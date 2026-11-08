"""Dictionary trail digests (each column's computation at the last update) and the run score card.

Revision ID: 202611080101
Revises: 202611070002
Create Date: 2026-11-08 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202611080101"
down_revision: str | None = "202611070002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dictionary_sync_run",
        sa.Column(
            "score",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="The update's score card: mechanical checks, the verifier's sample, the verdict.",
        ),
    )
    op.create_table(
        "dictionary_trail_digest",
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            sa.ForeignKey("tenant.tenant_id", ondelete="CASCADE"),
            primary_key=True,
            comment="Tenant whose dictionary the digest belongs to; references tenant.tenant_id.",
        ),
        sa.Column("table_key", sa.Text(), primary_key=True, comment="Folded DB.Schema.Object key."),
        sa.Column("column_name", sa.Text(), primary_key=True, comment="Folded column name."),
        sa.Column(
            "digest",
            sa.String(64),
            nullable=False,
            comment="Digest of the column's lineage steps and its object's filters; no code text.",
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        comment=(
            "Each dictionary column's code trail digest at the last update, kept apart from the "
            "versions so a run that writes no version still remembers it (011-dictionary-sync)."
        ),
    )


def downgrade() -> None:
    op.drop_table("dictionary_trail_digest")
    op.drop_column("dictionary_sync_run", "score")
