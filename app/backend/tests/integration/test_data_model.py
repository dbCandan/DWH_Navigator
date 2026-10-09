"""The migrated account schema (application-foundation/PRDs/001-user-accounts Veri ve geçiş).

The migration seeds the platform tenant and both application roles with the baseline permission;
the database itself refuses an invalid username, a display name outside its bounds, an expiring
one-time password without a pending change, and a password history row that carries a value.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.session import async_session_factory
from app.domain.models.permission import Permission, RolePermission
from app.domain.models.role import Role
from app.domain.models.tenant import Tenant
from tests.integration.conftest import AuthHarness

pytestmark = pytest.mark.integration


async def test_the_migration_seeds_the_tenant_roles_and_permissions(
    migrated_database: None,
) -> None:
    async with async_session_factory() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.code == "platform"))
        ).scalar_one()
        roles = dict(
            (
                await session.execute(
                    select(Role.code, Role.name).where(
                        Role.code.in_(["kullanici", "yonetici", "super_admin"])
                    )
                )
            ).all()
        )
        granted = (
            (
                await session.execute(
                    select(Role.code)
                    .join(RolePermission, RolePermission.role_id == Role.role_id)
                    .join(Permission, Permission.permission_id == RolePermission.permission_id)
                    .where(Permission.code == "platform:access")
                )
            )
            .scalars()
            .all()
        )
    assert tenant.public_id == "00000000-0000-4000-8000-000000000010"
    assert tenant.is_active
    assert roles == {"kullanici": "Kullanıcı", "yonetici": "Yönetici", "super_admin": "Super Admin"}
    assert set(granted) == {"kullanici", "yonetici", "super_admin"}


async def _refused(statement: str, **parameters: object) -> None:
    async with async_session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text(statement), parameters)
        await session.rollback()


async def test_the_database_enforces_the_account_rules(auth: AuthHarness) -> None:
    admin = await auth.super_admin()
    async with async_session_factory() as session:
        user_id, tenant_id = (
            await session.execute(
                text("SELECT user_id, home_tenant_id FROM app_user WHERE username = :name"),
                {"name": admin.username},
            )
        ).one()

    insert_user = (
        "INSERT INTO app_user (public_id, home_tenant_id, username, display_name, password_hash, "
        "password_change_required, one_time_password_expires_at) VALUES "
        "(gen_random_uuid()::text, :tenant, :name, :display, 'x', :pending, :expires)"
    )
    for name, display, pending, expires in (
        ("Upper.Case", "Ad", False, None),
        ("ayşe", "Ad", False, None),
        ("ab", "Ad", False, None),
        ("valid.name.one", "", False, None),
        ("valid.name.two", "x" * 129, False, None),
        ("valid.name.three", "Ad", False, datetime(2030, 1, 1, tzinfo=UTC)),
    ):
        await _refused(
            insert_user,
            tenant=tenant_id,
            name=name,
            display=display,
            pending=pending,
            expires=expires,
        )

    insert_change = (
        "INSERT INTO app_user_change (tenant_id, actor_user_id, target_user_id, changed_field, "
        "old_value, new_value) VALUES (:tenant, :user, :user, :field, :old, :new)"
    )
    for field, old, new in (
        ("password", None, "secret-value"),
        ("password", "old-secret", "changed"),
        ("email", None, "x"),
    ):
        await _refused(insert_change, tenant=tenant_id, user=user_id, field=field, old=old, new=new)


async def test_the_change_history_has_no_update_or_soft_delete_columns(
    migrated_database: None,
) -> None:
    async with async_session_factory() as session:
        columns = set(
            (
                await session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'app_user_change'"
                    )
                )
            ).scalars()
        )
    assert {"updated_at", "updated_by", "is_deleted", "deleted_at", "deleted_by"}.isdisjoint(
        columns
    )
    assert {"created_at", "created_by", "props"} <= columns
