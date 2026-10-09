"""Application user: a local account with a password the application hashes and checks."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id


class User(AuditSoftDeleteMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = (
        Index(
            "ix_app_user_active_public_id",
            "public_id",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("username ~ '^[a-z0-9._-]{3,64}$'", name="username_format"),
        CheckConstraint("char_length(display_name) BETWEEN 1 AND 128", name="display_name_length"),
        # A one-time password expires only while the account still waits for its own password.
        CheckConstraint(
            "one_time_password_expires_at IS NULL OR password_change_required",
            name="one_time_password_expiry_needs_change",
        ),
        {
            "comment": (
                "Local application account of the application-foundation context, opened by the "
                "super admin or by the super admin bootstrap. Accounts are never deleted, only "
                "deactivated. Credentials never cross the API boundary."
            )
        },
    )

    user_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        Text,
        default=new_public_id,
        nullable=False,
        unique=True,
    )
    home_tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant that scopes the user's role assignments; references tenant.tenant_id.",
    )
    username: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        unique=True,
        comment=(
            "Login name after NFKC, trimming and lower-casing: 3-64 characters of a-z, 0-9, "
            "'.', '_' and '-'; unique across active and inactive accounts."
        ),
    )
    email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
        unique=True,
        comment=(
            "Optional lower-case e-mail; unique when present. Opening an account does not ask "
            "for it and login never uses it."
        ),
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name shown in the interface and records; 1-128 characters, no control character.",
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Argon2 hash of the current password, or of the one-time password while "
            "password_change_required is true."
        ),
    )
    password_change_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment=(
            "True while the account waits for the person's own password: after the super admin "
            "opened or reset it, or after the super admin bootstrap or operator command set it. "
            "Login answers password_change_required until the password is changed."
        ),
    )
    one_time_password_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "UTC expiry of the one-time password the super admin received; empty when the "
            "password does not expire (bootstrap and operator command) or no change is pending."
        ),
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC time the person last set their own password; empty until the first change.",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC time a session was last opened by login or password change.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment=(
            "False after the super admin deactivates the account; an inactive account cannot "
            "log in, change its password or refresh a session."
        ),
    )
