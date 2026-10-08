"""Add the changed search and answer settings (search_setting).

Expand-only: it adds one table and changes no existing table; with no row every setting has its
measured default. Downgrade drops the table and every changed value; the defaults apply again.

Spec: data-dictionary/PRDs/009-search-settings (Veri ve geçiş).

Revision ID: 202610080005
Revises: 202610080004
Create Date: 2026-10-08 19:52:29.608816
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610080005"
down_revision: str | None = "202610080004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_setting",
        sa.Column(
            "search_setting_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "setting_key",
            sa.String(length=64),
            nullable=False,
            comment="Dotted key of the settings schema (app.services.search_settings_schema), e.g. 'analyst.shortlist'; the process refuses to start on a key the schema lacks.",
        ),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="The JSON value (true/false or a number) within the field's type and range.",
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_search_setting_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("search_setting_id", name=op.f("pk_search_setting")),
        comment="A search or answer setting of the data-dictionary context (search-settings capability) whose value differs from the code's measured default, one non-deleted row per tenant and key. A value set back to its default soft-deletes the row. updated_by is the user who saved the value.",
    )
    op.create_index(
        op.f("ix_search_setting_tenant_id"),
        "search_setting",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "uq_search_setting_tenant_key",
        "search_setting",
        ["tenant_id", "setting_key"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_search_setting_tenant_key",
        table_name="search_setting",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_index(op.f("ix_search_setting_tenant_id"), table_name="search_setting")
    op.drop_table("search_setting")
