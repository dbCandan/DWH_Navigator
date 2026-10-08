"""Append-only history of account, role, activation and password changes."""

from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AppendOnlyAuditMixin


class UserChangeField(StrEnum):
    """The account attribute a history row records (application-foundation 001 Requirement 5)."""

    ACCOUNT = "account"
    ROLE = "role"
    ACTIVE = "active"
    PASSWORD = "password"


class PasswordKind(StrEnum):
    """The only content of a password row: who set the password, never the password itself."""

    CHANGED = "changed"
    RESET = "reset"


class UserChange(AppendOnlyAuditMixin, Base):
    __tablename__ = "app_user_change"
    __table_args__ = (
        Index("ix_app_user_change_target_created", "target_user_id", "created_at"),
        CheckConstraint(
            "changed_field IN ('account', 'role', 'active', 'password')",
            name="changed_field_allowed",
        ),
        # A password row carries no value, only whether the person changed it or it was reset.
        CheckConstraint(
            "changed_field <> 'password' OR (old_value IS NULL AND new_value IN "
            "('changed', 'reset'))",
            name="password_row_has_no_value",
        ),
        {
            "comment": (
                "Append-only history of changes to a local account, written in the same "
                "transaction as the change; owned by the application-foundation context. The "
                "application only inserts rows: no update or soft-delete path exists. created_at "
                "is the change time and created_by the actor."
            )
        },
    )

    app_user_change_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant in which the change happened; references tenant.tenant_id.",
    )
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment=(
            "Account that made the change; references app_user.user_id. The account itself when "
            "the deployment bootstrap or the operator command made it, or the person changed "
            "their own password."
        ),
    )
    target_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Account that changed; references app_user.user_id.",
    )
    changed_field: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=(
            "Changed attribute; code reflection app.domain.models.user_change.UserChangeField: "
            "'account' = account opened, 'role' = application or super admin role, "
            "'active' = activation, 'password' = password changed or reset."
        ),
    )
    old_value: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment=(
            "Value before the change: a role code ('kullanici', 'yonetici', 'super_admin') or "
            "'true'/'false' for activation; empty for 'account' and 'password' rows and when the "
            "account held no such role."
        ),
    )
    new_value: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=(
            "Value after the change: the role the account was opened with for 'account', a role "
            "code for 'role', 'true'/'false' for 'active', and for 'password' only the kind, code "
            "reflection app.domain.models.user_change.PasswordKind: 'changed' = the person "
            "set it, 'reset' = the super admin or operator command reset it."
        ),
    )
