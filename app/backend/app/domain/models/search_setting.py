"""Changed search and answer settings (data-dictionary 009-search-settings).

A row keeps one setting whose value differs from the code's measured default; the effective value
is the default with the stored value on top. A value set back to its default soft-deletes its row.
The row is a key-value mapping identified by its stable natural key, so it carries no public_id
(rules/41's form for mapping tables).
"""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin


class SearchSetting(AuditSoftDeleteMixin, Base):
    __tablename__ = "search_setting"
    __table_args__ = (
        Index(
            "uq_search_setting_tenant_key",
            "tenant_id",
            "setting_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {
            "comment": (
                "A search or answer setting of the data-dictionary context (search-settings "
                "capability) whose value differs from the code's measured default, one "
                "non-deleted row per tenant and key. A value set back to its default "
                "soft-deletes the row. updated_by is the user who saved the value."
            )
        },
    )

    search_setting_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    setting_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "Dotted key of the settings schema (app.services.search_settings_schema), e.g. "
            "'analyst.shortlist'; the process refuses to start on a key the schema lacks."
        ),
    )
    value: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        comment="The JSON value (true/false or a number) within the field's type and range.",
    )
