"""The visitor: a person on the main screen without an account (application-foundation
003-anonymous-visitor Decision 1, 2, 5).

A visitor is known by the random device id its browser sends; only the SHA-256 of that id is kept,
so the table never holds the id itself. The last address and host name are what the visitor's
latest request showed. A visitor is not an account and never appears in user management.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id

ADDRESS_MAX_CHARS = 45
HOST_MAX_CHARS = 255


class Visitor(AuditSoftDeleteMixin, Base):
    __tablename__ = "visitor"
    __table_args__ = (
        Index(
            "ix_visitor_active_public_id",
            "public_id",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("device_key ~ '^[0-9a-f]{64}$'", name="device_key_format"),
        {
            "comment": (
                "A person who uses the main screen without an account (application-foundation "
                "context, anonymous-visitor capability). Known by the SHA-256 of the random device "
                "id its browser keeps; owns its analyses, term lists and votes. Not an account: "
                "it has no role and never appears in user management."
            )
        },
    )

    visitor_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36),
        default=new_public_id,
        nullable=False,
        unique=True,
        comment="The visitor's own random id (UUID), unrelated to the device id it sends.",
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Owning tenant (the single platform tenant); references tenant.tenant_id.",
    )
    device_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment=(
            "Lower-case hex SHA-256 of the device id the browser sends in X-Device-Id; the id "
            "itself is never stored."
        ),
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="The visitor's first request (UTC).",
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="The visitor's latest request (UTC).",
    )
    last_address: Mapped[str] = mapped_column(
        String(ADDRESS_MAX_CHARS),
        nullable=False,
        comment=(
            "The client IP address of the latest request, resolved through the trusted ingress "
            "networks only (personal data)."
        ),
    )
    last_host: Mapped[str | None] = mapped_column(
        String(HOST_MAX_CHARS),
        nullable=True,
        comment=(
            "The host name the reverse DNS lookup of last_address returned; empty when none "
            "(personal data)."
        ),
    )
