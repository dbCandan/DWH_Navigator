"""Add the dictionary versions and their imported records.

Expand-only: it adds dictionary_version, dictionary_object_record and dictionary_column_record and
changes no existing table. No data is moved: the dictionary is imported from the admin screen.
Downgrade drops the three tables and every imported dictionary; the application then starts with
an empty dictionary until a workbook is imported again.

Spec: data-dictionary/PRDs/001-dictionary-management (Veri ve geçiş).

Revision ID: 202610080003
Revises: 202610080002
Create Date: 2026-10-08 19:52:29.608816
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610080003"
down_revision: str | None = "202610080002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dictionary_version",
        sa.Column(
            "dictionary_version_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="Code reflection app.domain.dictionary.DictionaryStatus: 'active' = the dictionary every capability reads; 'previous' = the version the active one replaced, records kept; 'pruned' = an older version, records deleted and row soft-deleted.",
        ),
        sa.Column(
            "version",
            sa.String(length=64),
            nullable=False,
            comment="Dictionary version '<12 hex digits of the workbook's SHA-256>-<Kolonlar record count>'; not unique: the same workbook imported again yields the same number.",
        ),
        sa.Column(
            "content_digest",
            sa.String(length=12),
            nullable=False,
            comment="First 12 hex digits of the SHA-256 of the records' key-sorted JSON; an import with the active version's digest creates no version. The read function recomputes it.",
        ),
        sa.Column(
            "source_name",
            sa.String(length=255),
            nullable=False,
            comment="Name of the imported workbook without folders and control characters.",
        ),
        sa.Column(
            "channel",
            sa.String(length=8),
            nullable=False,
            comment="Code reflection app.domain.dictionary.ImportChannel: 'arayuz' = admin screen, 'betik' = backend script.",
        ),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC time of the import.",
        ),
        sa.Column(
            "row_count",
            sa.Integer(),
            nullable=False,
            comment="Kolonlar records of the workbook, empty and invalid rows included.",
        ),
        sa.Column(
            "column_count",
            sa.Integer(),
            nullable=False,
            comment="Valid, distinct columns the engine reads.",
        ),
        sa.Column(
            "object_count",
            sa.Integer(),
            nullable=False,
            comment="Tables (DB.Schema.Object) of the valid columns.",
        ),
        sa.Column(
            "warning_count",
            sa.Integer(),
            nullable=False,
            comment="Every warning of the import.",
        ),
        sa.Column(
            "warnings",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
            comment="The first 20 warning texts, in import order.",
        ),
        sa.Column(
            "object_extra_headers",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
            comment="Objeler headers outside the template, in header order (the export order).",
        ),
        sa.Column(
            "column_extra_headers",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
            comment="Kolonlar headers outside the template, in header order (the export order).",
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
            "(status = 'pruned') = is_deleted",
            name=op.f("ck_dictionary_version_pruned_is_deleted"),
        ),
        sa.CheckConstraint(
            "channel IN ('arayuz', 'betik')",
            name=op.f("ck_dictionary_version_channel_allowed"),
        ),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{12}$'",
            name=op.f("ck_dictionary_version_content_digest_format"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'previous', 'pruned')",
            name=op.f("ck_dictionary_version_status_allowed"),
        ),
        sa.CheckConstraint(
            "char_length(source_name) BETWEEN 1 AND 255",
            name=op.f("ck_dictionary_version_source_name_length"),
        ),
        sa.CheckConstraint(
            "row_count >= 0 AND column_count >= 0 AND object_count >= 0 AND warning_count >= 0",
            name=op.f("ck_dictionary_version_counts_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_dictionary_version_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("dictionary_version_id", name=op.f("pk_dictionary_version")),
        sa.UniqueConstraint("public_id", name=op.f("uq_dictionary_version_public_id")),
        comment="One import of the data dictionary (data-dictionary context, dictionary-management capability). The tenant has at most one active version, which every capability reads, and keeps the records of at most one previous version; an older version is pruned: its records are deleted and this row stays soft-deleted. created_by is the importing user (empty for the backend script); created_at and imported_at are the import time.",
    )
    op.create_index(
        "ix_dictionary_version_active_public_id",
        "dictionary_version",
        ["public_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        op.f("ix_dictionary_version_tenant_id"),
        "dictionary_version",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "uq_dictionary_version_tenant_active",
        "dictionary_version",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND is_deleted = false"),
    )
    op.create_index(
        "uq_dictionary_version_tenant_previous",
        "dictionary_version",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'previous' AND is_deleted = false"),
    )
    op.create_table(
        "dictionary_column_record",
        sa.Column(
            "dictionary_version_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning version; references dictionary_version.dictionary_version_id.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="0-based position of the record in its sheet; the engine's column order.",
        ),
        sa.Column(
            "database_name",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field DatabaseName.",
        ),
        sa.Column(
            "schema_name",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field SchemaName.",
        ),
        sa.Column(
            "object_name",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field ObjectName.",
        ),
        sa.Column(
            "column_name",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field ColumnName.",
        ),
        sa.Column(
            "column_description",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field ColumnDescription.",
        ),
        sa.Column(
            "synonyms",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field Synonyms (raw cell text).",
        ),
        sa.Column(
            "role",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field Role (not validated).",
        ),
        sa.Column(
            "summary",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field Summary (not validated).",
        ),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="Key 'extra_cells': header -> cell text of the non-empty extra columns.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dictionary_version_id"],
            ["dictionary_version.dictionary_version_id"],
            name=op.f("fk_dictionary_column_record_dictionary_version_id_dictionary_version"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "dictionary_version_id",
            "position",
            name=op.f("pk_dictionary_column_record"),
        ),
        comment="One Kolonlar row of a dictionary version as imported: cell texts under the template field names, empty cells as ''; duplicate and invalid rows included. Insert-only part of the version; deleted with it when the version is pruned (dictionary-management Decision 8).",
    )
    op.create_index(
        "ix_dictionary_column_record_table",
        "dictionary_column_record",
        ["dictionary_version_id", "database_name", "schema_name", "object_name"],
        unique=False,
    )
    op.create_table(
        "dictionary_object_record",
        sa.Column(
            "dictionary_version_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning version; references dictionary_version.dictionary_version_id.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="0-based position of the record in its sheet; the engine's column order.",
        ),
        sa.Column(
            "object_key",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field ObjectKey.",
        ),
        sa.Column(
            "database_name",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field DatabaseName.",
        ),
        sa.Column(
            "schema_name",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field SchemaName.",
        ),
        sa.Column(
            "object_name",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field ObjectName.",
        ),
        sa.Column(
            "object_description",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field ObjectDescription.",
        ),
        sa.Column(
            "grain",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field Grain.",
        ),
        sa.Column(
            "key_columns",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field KeyColumns.",
        ),
        sa.Column(
            "time_columns",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field TimeColumns.",
        ),
        sa.Column(
            "business_domain",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field BusinessDomain.",
        ),
        sa.Column(
            "dataset_group",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Template field DatasetGroup.",
        ),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="Key 'extra_cells': header -> cell text of the non-empty extra columns.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dictionary_version_id"],
            ["dictionary_version.dictionary_version_id"],
            name=op.f("fk_dictionary_object_record_dictionary_version_id_dictionary_version"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "dictionary_version_id",
            "position",
            name=op.f("pk_dictionary_object_record"),
        ),
        comment="One Objeler row of a dictionary version as imported: cell texts under the template field names, empty cells as ''. Insert-only part of the version; deleted with it when the version is pruned (dictionary-management Decision 8).",
    )


def downgrade() -> None:
    op.drop_table("dictionary_object_record")
    op.drop_index("ix_dictionary_column_record_table", table_name="dictionary_column_record")
    op.drop_table("dictionary_column_record")
    op.drop_index(
        "uq_dictionary_version_tenant_previous",
        table_name="dictionary_version",
        postgresql_where=sa.text("status = 'previous' AND is_deleted = false"),
    )
    op.drop_index(
        "uq_dictionary_version_tenant_active",
        table_name="dictionary_version",
        postgresql_where=sa.text("status = 'active' AND is_deleted = false"),
    )
    op.drop_index(op.f("ix_dictionary_version_tenant_id"), table_name="dictionary_version")
    op.drop_index(
        "ix_dictionary_version_active_public_id",
        table_name="dictionary_version",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("dictionary_version")
