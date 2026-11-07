"""Dictionary versions and their imported records (data-dictionary 001-dictionary-management).

A version row describes one import; the Objeler and Kolonlar records keep the workbook's cell
texts under the template's field names, in sheet order. Record rows are the immutable, insert-only
part of a version: they carry no public_id, update or soft-delete columns, and the service deletes
them in the same transaction that prunes their version (Decision 8, the PRD's deviation from
rules/41 and rules/42).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.dictionary import SOURCE_NAME_MAX_LENGTH
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id

_TEXT_DEFAULT = text("''")


def _cell_column(comment: str) -> Mapped[str]:
    return mapped_column(
        Text, nullable=False, default="", server_default=_TEXT_DEFAULT, comment=comment
    )


class DictionaryVersion(AuditSoftDeleteMixin, Base):
    __tablename__ = "dictionary_version"
    __table_args__ = (
        Index(
            "ix_dictionary_version_active_public_id",
            "public_id",
            postgresql_where=text("is_deleted = false"),
        ),
        # At most one active version per tenant; replaced versions are kept for a month.
        Index(
            "uq_dictionary_version_tenant_active",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'active' AND is_deleted = false"),
        ),
        CheckConstraint(
            "status IN ('active', 'previous', 'pending', 'pruned')", name="status_allowed"
        ),
        CheckConstraint("(status = 'pruned') = is_deleted", name="pruned_is_deleted"),
        CheckConstraint(
            "channel IN ('arayuz', 'betik', 'kaynak', 'geri_donus')", name="channel_allowed"
        ),
        CheckConstraint("content_digest ~ '^[0-9a-f]{12}$'", name="content_digest_format"),
        CheckConstraint(
            f"char_length(source_name) BETWEEN 1 AND {SOURCE_NAME_MAX_LENGTH}",
            name="source_name_length",
        ),
        CheckConstraint(
            "row_count >= 0 AND column_count >= 0 AND object_count >= 0 AND warning_count >= 0",
            name="counts_not_negative",
        ),
        {
            "comment": (
                "One import of the data dictionary (data-dictionary context, dictionary-management "
                "capability). The tenant has at most one active version, which every capability "
                "reads, and keeps the records of at most one previous version; an older version is "
                "pruned: its records are deleted and this row stays soft-deleted. created_by is "
                "the importing user (empty for the backend script); created_at and imported_at "
                "are the import time."
            )
        },
    )

    dictionary_version_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(Text, default=new_public_id, nullable=False, unique=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=(
            "Code reflection app.domain.dictionary.DictionaryStatus: 'active' = the dictionary "
            "every capability reads; 'previous' = the version the active one replaced, records "
            "kept; 'pruned' = an older version, records deleted and row soft-deleted."
        ),
    )
    version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "Dictionary version '<12 hex digits of the workbook's SHA-256>-<Kolonlar record "
            "count>'; not unique: the same workbook imported again yields the same number."
        ),
    )
    content_digest: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        comment=(
            "First 12 hex digits of the SHA-256 of the records' key-sorted JSON; an import with "
            "the active version's digest creates no version. The read function recomputes it."
        ),
    )
    source_name: Mapped[str] = mapped_column(
        String(SOURCE_NAME_MAX_LENGTH),
        nullable=False,
        comment="Name of the imported workbook without folders and control characters.",
    )
    channel: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Code reflection app.domain.dictionary.ImportChannel: 'arayuz' = admin screen, "
        "'betik' = backend script, 'kaynak' = warehouse sync, 'geri_donus' = rollback.",
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this version stopped being active; the 30 day retention starts here.",
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="UTC time of the import."
    )
    row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Kolonlar records of the workbook, empty and invalid rows included.",
    )
    column_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Valid, distinct columns the engine reads."
    )
    object_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Tables (DB.Schema.Object) of the valid columns.",
    )
    warning_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Every warning of the import."
    )
    warnings: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
        comment="The first 20 warning texts, in import order.",
    )
    object_extra_headers: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
        comment="Objeler headers outside the template, in header order (the export order).",
    )
    column_extra_headers: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
        comment="Kolonlar headers outside the template, in header order (the export order).",
    )


def _version_column() -> Mapped[int]:
    return mapped_column(
        BigInteger,
        ForeignKey("dictionary_version.dictionary_version_id", ondelete="RESTRICT"),
        primary_key=True,
        comment="Owning version; references dictionary_version.dictionary_version_id.",
    )


def _position_column() -> Mapped[int]:
    return mapped_column(
        Integer,
        primary_key=True,
        comment="0-based position of the record in its sheet; the engine's column order.",
    )


def _props_column() -> Mapped[dict[str, Any]]:
    return mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="Key 'extra_cells': header -> cell text of the non-empty extra columns.",
    )


def _created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class DictionaryObjectRecord(Base):
    __tablename__ = "dictionary_object_record"
    __table_args__ = (
        {
            "comment": (
                "One Objeler row of a dictionary version as imported: cell texts under the "
                "template field names, empty cells as ''. Insert-only part of the version; "
                "deleted with it when the version is pruned (dictionary-management Decision 8)."
            )
        },
    )

    dictionary_version_id: Mapped[int] = _version_column()
    position: Mapped[int] = _position_column()
    object_key: Mapped[str] = _cell_column("Template field ObjectKey.")
    database_name: Mapped[str] = _cell_column("Template field DatabaseName.")
    schema_name: Mapped[str] = _cell_column("Template field SchemaName.")
    object_name: Mapped[str] = _cell_column("Template field ObjectName.")
    object_description: Mapped[str] = _cell_column("Template field ObjectDescription.")
    grain: Mapped[str] = _cell_column("Template field Grain.")
    key_columns: Mapped[str] = _cell_column("Template field KeyColumns.")
    time_columns: Mapped[str] = _cell_column("Template field TimeColumns.")
    business_domain: Mapped[str] = _cell_column("Template field BusinessDomain.")
    dataset_group: Mapped[str] = _cell_column("Template field DatasetGroup.")
    props: Mapped[dict[str, Any]] = _props_column()
    created_at: Mapped[datetime] = _created_at_column()


class DictionaryColumnRecord(Base):
    __tablename__ = "dictionary_column_record"
    __table_args__ = (
        # Requirement 18: the records of one table of a version.
        Index(
            "ix_dictionary_column_record_table",
            "dictionary_version_id",
            "database_name",
            "schema_name",
            "object_name",
        ),
        {
            "comment": (
                "One Kolonlar row of a dictionary version as imported: cell texts under the "
                "template field names, empty cells as ''; duplicate and invalid rows included. "
                "Insert-only part of the version; deleted with it when the version is pruned "
                "(dictionary-management Decision 8)."
            )
        },
    )

    dictionary_version_id: Mapped[int] = _version_column()
    position: Mapped[int] = _position_column()
    database_name: Mapped[str] = _cell_column("Template field DatabaseName.")
    schema_name: Mapped[str] = _cell_column("Template field SchemaName.")
    object_name: Mapped[str] = _cell_column("Template field ObjectName.")
    column_name: Mapped[str] = _cell_column("Template field ColumnName.")
    column_description: Mapped[str] = _cell_column("Template field ColumnDescription.")
    synonyms: Mapped[str] = _cell_column("Template field Synonyms (raw cell text).")
    role: Mapped[str] = _cell_column("Template field Role (not validated).")
    summary: Mapped[str] = _cell_column("Template field Summary (not validated).")
    props: Mapped[dict[str, Any]] = _props_column()
    created_at: Mapped[datetime] = _created_at_column()


# Template field name -> record column, in template order (Requirement 1).
OBJECT_FIELD_COLUMNS = {
    "ObjectKey": "object_key",
    "DatabaseName": "database_name",
    "SchemaName": "schema_name",
    "ObjectName": "object_name",
    "ObjectDescription": "object_description",
    "Grain": "grain",
    "KeyColumns": "key_columns",
    "TimeColumns": "time_columns",
    "BusinessDomain": "business_domain",
    "DatasetGroup": "dataset_group",
}
COLUMN_FIELD_COLUMNS = {
    "DatabaseName": "database_name",
    "SchemaName": "schema_name",
    "ObjectName": "object_name",
    "ColumnName": "column_name",
    "ColumnDescription": "column_description",
    "Synonyms": "synonyms",
    "Role": "role",
    "Summary": "summary",
}
