"""Add local accounts, refresh sessions and the account change history.

Expand-only: it adds tables, defaulted or nullable columns and constraints that the existing rows
already satisfy, and it makes app_user.email optional. It seeds the single platform tenant, the two
application roles and their baseline permission, so the super admin bootstrap and account creation
work without creating a tenant. Downgrade refuses while an account has no e-mail, because the
previous schema requires one.

Spec: application-foundation/PRDs/001-user-accounts (Veri ve geçiş).

Revision ID: 202610080001
Revises: 202608060001
Create Date: 2026-10-08 18:04:13.977831
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610080001"
down_revision: str | None = "202608060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Stable identifiers of the seeded rows, so every database addresses them alike.
_PLATFORM_TENANT_PUBLIC_ID = "00000000-0000-4000-8000-000000000010"
_USER_ROLE_PUBLIC_ID = "00000000-0000-4000-8000-000000000011"
_MANAGER_ROLE_PUBLIC_ID = "00000000-0000-4000-8000-000000000012"


def upgrade() -> None:
    op.create_table(
        "app_user_change",
        sa.Column("app_user_change_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Tenant in which the change happened; references tenant.tenant_id.",
        ),
        sa.Column(
            "actor_user_id",
            sa.BigInteger(),
            nullable=False,
            comment="Account that made the change; references app_user.user_id. The account itself when the deployment bootstrap or the operator command made it, or the person changed their own password.",
        ),
        sa.Column(
            "target_user_id",
            sa.BigInteger(),
            nullable=False,
            comment="Account that changed; references app_user.user_id.",
        ),
        sa.Column(
            "changed_field",
            sa.String(length=16),
            nullable=False,
            comment="Changed attribute; code reflection app.domain.models.user_change.UserChangeField: 'account' = account opened, 'role' = application or super admin role, 'active' = activation, 'password' = password changed or reset.",
        ),
        sa.Column(
            "old_value",
            sa.String(length=32),
            nullable=True,
            comment="Value before the change: a role code ('kullanici', 'yonetici', 'super_admin') or 'true'/'false' for activation; empty for 'account' and 'password' rows and when the account held no such role.",
        ),
        sa.Column(
            "new_value",
            sa.String(length=32),
            nullable=False,
            comment="Value after the change: the role the account was opened with for 'account', a role code for 'role', 'true'/'false' for 'active', and for 'password' only the kind, code reflection app.domain.models.user_change.PasswordKind: 'changed' = the person set it, 'reset' = the super admin or operator command reset it.",
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
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "changed_field <> 'password' OR (old_value IS NULL AND new_value IN ('changed', 'reset'))",
            name=op.f("ck_app_user_change_password_row_has_no_value"),
        ),
        sa.CheckConstraint(
            "changed_field IN ('account', 'role', 'active', 'password')",
            name=op.f("ck_app_user_change_changed_field_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_user_change_actor_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_user_change_target_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_app_user_change_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("app_user_change_id", name=op.f("pk_app_user_change")),
        comment="Append-only history of changes to a local account, written in the same transaction as the change; owned by the application-foundation context. The application only inserts rows: no update or soft-delete path exists. created_at is the change time and created_by the actor.",
    )
    op.create_index(
        op.f("ix_app_user_change_actor_user_id"), "app_user_change", ["actor_user_id"], unique=False
    )
    op.create_index(
        "ix_app_user_change_target_created",
        "app_user_change",
        ["target_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_user_change_tenant_id"), "app_user_change", ["tenant_id"], unique=False
    )
    op.create_table(
        "auth_refresh_session",
        sa.Column(
            "auth_refresh_session_id", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Tenant of the signed-in user; references tenant.tenant_id.",
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            nullable=False,
            comment="Signed-in user; references app_user.user_id.",
        ),
        sa.Column(
            "family_id",
            sa.Uuid(),
            nullable=False,
            comment="Session family: every token issued from one login and its rotations.",
        ),
        sa.Column(
            "token_sha256",
            sa.String(length=64),
            nullable=False,
            comment="Lower-case hex SHA-256 digest of the refresh token; the token is never stored.",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time the token was presented and rotated; empty while unused.",
        ),
        sa.Column(
            "idle_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC time the unused token expires for inactivity (60 minutes after issue).",
        ),
        sa.Column(
            "absolute_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC upper bound of the whole family (8 hours after login); never extended.",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time the token stopped being usable; empty while usable.",
        ),
        sa.Column(
            "revoke_reason",
            sa.String(length=32),
            nullable=True,
            comment="Why the token ended; code reflection app.domain.models.refresh_session.RefreshSessionEndReason: 'rotated' = replaced by its successor, 'logout' = user logged out, 'reuse_detected' = an ended token was presented again, 'authorization_changed' = role or activation changed, 'password_changed' = the password was changed or reset.",
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
            "revoke_reason IS NULL OR revoke_reason IN ('rotated', 'logout', 'reuse_detected', 'authorization_changed', 'password_changed')",
            name=op.f("ck_auth_refresh_session_revoke_reason_allowed"),
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoke_reason IS NULL)",
            name=op.f("ck_auth_refresh_session_revocation_is_complete"),
        ),
        sa.CheckConstraint(
            "idle_expires_at <= absolute_expires_at",
            name=op.f("ck_auth_refresh_session_idle_within_absolute"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_auth_refresh_session_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_auth_refresh_session_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("auth_refresh_session_id", name=op.f("pk_auth_refresh_session")),
        sa.UniqueConstraint("token_sha256", name=op.f("uq_auth_refresh_session_token_sha256")),
        comment="One row per issued refresh token of the application-foundation context. Rows of one login share family_id; each refresh ends the presented row as 'rotated' and inserts its successor. Presenting an ended row ends the whole family as 'reuse_detected'. The token itself is never stored, only its SHA-256 digest. Rows whose end or expiry is older than seven days are deleted permanently by the login flow, so token digests are not kept longer than needed.",
    )
    op.create_index(
        "ix_auth_refresh_session_absolute_expires_at",
        "auth_refresh_session",
        ["absolute_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_refresh_session_active_family",
        "auth_refresh_session",
        ["family_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_auth_refresh_session_user_id", "auth_refresh_session", ["user_id"], unique=False
    )
    op.add_column(
        "app_user",
        sa.Column(
            "password_change_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True while the account waits for the person's own password: after the super admin opened or reset it, or after the super admin bootstrap or operator command set it. Login answers password_change_required until the password is changed.",
        ),
    )
    op.add_column(
        "app_user",
        sa.Column(
            "one_time_password_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC expiry of the one-time password the super admin received; empty when the password does not expire (bootstrap and operator command) or no change is pending.",
        ),
    )
    op.add_column(
        "app_user",
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time the person last set their own password; empty until the first change.",
        ),
    )
    op.add_column(
        "app_user",
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time a session was last opened by login or password change.",
        ),
    )
    op.alter_column(
        "app_user",
        "home_tenant_id",
        existing_type=sa.BIGINT(),
        comment="Tenant that scopes the user's role assignments; references tenant.tenant_id.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "username",
        existing_type=sa.VARCHAR(length=120),
        comment="Login name after NFKC, trimming and lower-casing: 3-64 characters of a-z, 0-9, '.', '_' and '-'; unique across active and inactive accounts.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "email",
        existing_type=sa.VARCHAR(length=320),
        nullable=True,
        comment="Optional lower-case e-mail; unique when present. Opening an account does not ask for it and login never uses it.",
    )
    op.alter_column(
        "app_user",
        "display_name",
        existing_type=sa.VARCHAR(length=255),
        comment="Name shown in the interface and records; 1-128 characters, no control character.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "password_hash",
        existing_type=sa.TEXT(),
        comment="Argon2 hash of the current password, or of the one-time password while password_change_required is true.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment="False after the super admin deactivates the account; an inactive account cannot log in, change its password or refresh a session.",
        existing_nullable=False,
        existing_server_default=sa.text("true"),
    )
    op.create_table_comment(
        "app_user",
        "Local application account of the application-foundation context, opened by the super admin or by the super admin bootstrap. Accounts are never deleted, only deactivated. Credentials never cross the API boundary.",
        existing_comment="Human application identity; credentials never cross the API boundary.",
        schema=None,
    )
    op.create_check_constraint(
        op.f("ck_app_user_username_format"), "app_user", "username ~ '^[a-z0-9._-]{3,64}$'"
    )
    op.create_check_constraint(
        op.f("ck_app_user_display_name_length"),
        "app_user",
        "char_length(display_name) BETWEEN 1 AND 128",
    )
    op.create_check_constraint(
        op.f("ck_app_user_one_time_password_expiry_needs_change"),
        "app_user",
        "one_time_password_expires_at IS NULL OR password_change_required",
    )

    op.execute(
        sa.text(
            "INSERT INTO tenant (public_id, code, name) VALUES (:public_id, 'platform', 'Platform') "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(public_id=_PLATFORM_TENANT_PUBLIC_ID)
    )
    op.execute(
        sa.text(
            "INSERT INTO app_role (public_id, code, name, scope, is_system) VALUES "
            "(:user_role, 'kullanici', 'Kullanıcı', 'tenant', true), "
            "(:manager_role, 'yonetici', 'Yönetici', 'tenant', true) "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(user_role=_USER_ROLE_PUBLIC_ID, manager_role=_MANAGER_ROLE_PUBLIC_ID)
    )
    op.execute(
        sa.text(
            "INSERT INTO app_role_permission (role_id, permission_id) "
            "SELECT app_role.role_id, app_permission.permission_id "
            "FROM app_role CROSS JOIN app_permission "
            "WHERE app_role.code IN ('kullanici', 'yonetici') "
            "AND app_permission.code = 'platform:access' "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    without_email = connection.execute(
        sa.text("SELECT count(*) FROM app_user WHERE email IS NULL")
    ).scalar_one()
    if without_email:
        raise RuntimeError(
            "downgrade refused: accounts without an e-mail exist and the previous schema "
            "requires one"
        )
    op.execute(
        sa.text(
            "DELETE FROM app_user_role WHERE role_id IN "
            "(SELECT role_id FROM app_role WHERE code IN ('kullanici', 'yonetici'))"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM app_role_permission WHERE role_id IN "
            "(SELECT role_id FROM app_role WHERE code IN ('kullanici', 'yonetici'))"
        )
    )
    op.execute(sa.text("DELETE FROM app_role WHERE code IN ('kullanici', 'yonetici')"))
    op.drop_constraint(
        op.f("ck_app_user_one_time_password_expiry_needs_change"), "app_user", type_="check"
    )
    op.drop_constraint(op.f("ck_app_user_display_name_length"), "app_user", type_="check")
    op.drop_constraint(op.f("ck_app_user_username_format"), "app_user", type_="check")
    op.create_table_comment(
        "app_user",
        "Human application identity; credentials never cross the API boundary.",
        existing_comment="Local application account of the application-foundation context, opened by the super admin or by the super admin bootstrap. Accounts are never deleted, only deactivated. Credentials never cross the API boundary.",
        schema=None,
    )
    op.alter_column(
        "app_user",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="False after the super admin deactivates the account; an inactive account cannot log in, change its password or refresh a session.",
        existing_nullable=False,
        existing_server_default=sa.text("true"),
    )
    op.alter_column(
        "app_user",
        "password_hash",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="Argon2 hash of the current password, or of the one-time password while password_change_required is true.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "display_name",
        existing_type=sa.VARCHAR(length=255),
        comment=None,
        existing_comment="Name shown in the interface and records; 1-128 characters, no control character.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "email",
        existing_type=sa.VARCHAR(length=320),
        nullable=False,
        comment=None,
        existing_comment="Optional lower-case e-mail; unique when present. Opening an account does not ask for it and login never uses it.",
    )
    op.alter_column(
        "app_user",
        "username",
        existing_type=sa.VARCHAR(length=120),
        comment=None,
        existing_comment="Login name after NFKC, trimming and lower-casing: 3-64 characters of a-z, 0-9, '.', '_' and '-'; unique across active and inactive accounts.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "home_tenant_id",
        existing_type=sa.BIGINT(),
        comment=None,
        existing_comment="Tenant that scopes the user's role assignments; references tenant.tenant_id.",
        existing_nullable=False,
    )
    op.drop_column("app_user", "last_login_at")
    op.drop_column("app_user", "password_changed_at")
    op.drop_column("app_user", "one_time_password_expires_at")
    op.drop_column("app_user", "password_change_required")
    op.drop_index("ix_auth_refresh_session_user_id", table_name="auth_refresh_session")
    op.drop_index(
        "ix_auth_refresh_session_active_family",
        table_name="auth_refresh_session",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_index("ix_auth_refresh_session_absolute_expires_at", table_name="auth_refresh_session")
    op.drop_table("auth_refresh_session")
    op.drop_index(op.f("ix_app_user_change_tenant_id"), table_name="app_user_change")
    op.drop_index("ix_app_user_change_target_created", table_name="app_user_change")
    op.drop_index(op.f("ix_app_user_change_actor_user_id"), table_name="app_user_change")
    op.drop_table("app_user_change")
