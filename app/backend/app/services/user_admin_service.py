"""Super-admin account list, creation, role, activation and password reset.

application-foundation/PRDs/001-user-accounts Requirement 2 and 5. Every request re-reads the
acting super admin from the database (Decision 20); every real change writes its append-only
history row in the same transaction and ends the target's refresh sessions. The one-time password
appears only in the creation or reset response.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.core.security import hash_password, new_one_time_password
from app.domain.accounts import SUPER_ADMIN_ROLE, account_role, application_role_of
from app.domain.models.refresh_session import RefreshSessionEndReason
from app.domain.models.tenant import Tenant
from app.domain.models.user import User
from app.domain.models.user_change import PasswordKind, UserChange, UserChangeField
from app.infrastructure.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.admin.users import OneTimePassword, UserCreated, UserPage, UserSummary
from app.schemas.auth.response import AccountRoleValue, ApplicationRoleValue
from app.services.request_scope import acting_user_with_role, active_tenant

logger = logging.getLogger("app.admin")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


def user_not_found() -> ApplicationError:
    return ApplicationError(status.HTTP_404_NOT_FOUND, "user_not_found", "Kullanıcı bulunamadı.")


def username_taken() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT, "username_taken", "Bu kullanıcı adı zaten kullanılıyor."
    )


def super_admin_protected() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "super_admin_protected",
        "Süper yönetici hesabının rolü, durumu ve parolası bu ekrandan değiştirilemez.",
    )


def own_account() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "own_account",
        "Kendi hesabınızı pasifleştiremezsiniz.",
    )


class UserAdminService:
    def __init__(self, session: AsyncSession, *, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.sessions = RefreshSessionRepository(session)

    async def list_users(
        self, context: RequestContext, *, page: int, size: int, query: str | None
    ) -> UserPage:
        tenant = await active_tenant(self.users, context)
        await acting_user_with_role(self.users, context, SUPER_ADMIN_ROLE)
        rows, total = await self.users.list_users(
            tenant_id=tenant.tenant_id,
            query=query.strip() if query and query.strip() else None,
            offset=(page - 1) * size,
            limit=size,
        )
        return UserPage(
            items=[_summary(row.user, row.roles) for row in rows],
            page=page,
            size=size,
            total=total,
        )

    async def create_user(
        self,
        context: RequestContext,
        *,
        username: str,
        display_name: str,
        role_code: ApplicationRoleValue,
    ) -> UserCreated:
        tenant = await active_tenant(self.users, context)
        actor = await acting_user_with_role(self.users, context, SUPER_ADMIN_ROLE)
        if await self.users.username_exists(username):
            raise username_taken()
        role = await self.users.get_role(role_code)
        if role is None:  # pragma: no cover - the migration seeds both roles
            raise RuntimeError("application role is missing; run the migrations")
        now = datetime.now(UTC)
        one_time_password = new_one_time_password()
        expires_at = now + timedelta(hours=self.settings.one_time_password_ttl_hours)
        try:
            # A concurrent request with the same name loses on the unique constraint.
            async with self.session.begin_nested():
                user = await self.users.add_user(
                    User(
                        home_tenant_id=tenant.tenant_id,
                        username=username,
                        display_name=display_name,
                        password_hash=hash_password(one_time_password),
                        password_change_required=True,
                        one_time_password_expires_at=expires_at,
                        is_active=True,
                        created_by=actor.user_id,
                        updated_by=actor.user_id,
                    )
                )
                await self.users.set_application_role(
                    user, role, actor_user_id=actor.user_id, now=now
                )
        except IntegrityError:
            raise username_taken() from None
        await self._record_change(
            tenant, actor, user, UserChangeField.ACCOUNT, old=None, new=role_code
        )
        log_event(
            logger,
            "admin.user.created",
            actor_public_id=actor.public_id,
            target_public_id=user.public_id,
            role=role_code,
        )
        return UserCreated(
            user=_summary(user, (role_code,)),
            one_time_password=one_time_password,
            one_time_password_expires_at=expires_at,
        )

    async def set_role(
        self, context: RequestContext, target_public_id: UUID, role_code: ApplicationRoleValue
    ) -> ApplicationRoleValue:
        tenant = await active_tenant(self.users, context)
        actor = await acting_user_with_role(self.users, context, SUPER_ADMIN_ROLE)
        target = await self._target(target_public_id, tenant)
        roles = await self.users.role_codes(target)
        if SUPER_ADMIN_ROLE in roles:
            raise super_admin_protected()
        current = application_role_of(roles)
        if current == role_code:
            return role_code
        role = await self.users.get_role(role_code)
        if role is None:  # pragma: no cover - the migration seeds both roles
            raise RuntimeError("application role is missing; run the migrations")
        now = datetime.now(UTC)
        await self.users.set_application_role(target, role, actor_user_id=actor.user_id, now=now)
        target.updated_by = actor.user_id
        await self._record_change(
            tenant, actor, target, UserChangeField.ROLE, old=current, new=role_code
        )
        await self._end_sessions(target, RefreshSessionEndReason.AUTHORIZATION_CHANGED, now)
        log_event(
            logger,
            "admin.user.role_changed",
            actor_public_id=actor.public_id,
            target_public_id=target.public_id,
            old_value=current,
            new_value=role_code,
        )
        return role_code

    async def set_active(
        self, context: RequestContext, target_public_id: UUID, active: bool
    ) -> bool:
        tenant = await active_tenant(self.users, context)
        actor = await acting_user_with_role(self.users, context, SUPER_ADMIN_ROLE)
        target = await self._target(target_public_id, tenant)
        if target.user_id == actor.user_id:
            raise own_account()
        if SUPER_ADMIN_ROLE in await self.users.role_codes(target):
            raise super_admin_protected()
        if target.is_active == active:
            return active
        now = datetime.now(UTC)
        old = target.is_active
        target.is_active = active
        target.updated_by = actor.user_id
        await self._record_change(
            tenant,
            actor,
            target,
            UserChangeField.ACTIVE,
            old=str(old).lower(),
            new=str(active).lower(),
        )
        await self._end_sessions(target, RefreshSessionEndReason.AUTHORIZATION_CHANGED, now)
        log_event(
            logger,
            "admin.user.active_changed",
            actor_public_id=actor.public_id,
            target_public_id=target.public_id,
            old_value=old,
            new_value=active,
        )
        return active

    async def reset_password(
        self, context: RequestContext, target_public_id: UUID
    ) -> OneTimePassword:
        tenant = await active_tenant(self.users, context)
        actor = await acting_user_with_role(self.users, context, SUPER_ADMIN_ROLE)
        target = await self._target(target_public_id, tenant)
        if SUPER_ADMIN_ROLE in await self.users.role_codes(target):
            raise super_admin_protected()
        now = datetime.now(UTC)
        one_time_password = new_one_time_password()
        expires_at = now + timedelta(hours=self.settings.one_time_password_ttl_hours)
        # The previous password stops working at once; the account waits for a new one.
        target.password_hash = hash_password(one_time_password)
        target.password_change_required = True
        target.one_time_password_expires_at = expires_at
        target.updated_by = actor.user_id
        await self._record_change(
            tenant,
            actor,
            target,
            UserChangeField.PASSWORD,
            old=None,
            new=PasswordKind.RESET.value,
        )
        await self._end_sessions(target, RefreshSessionEndReason.PASSWORD_CHANGED, now)
        log_event(
            logger,
            "admin.user.password_reset",
            actor_public_id=actor.public_id,
            target_public_id=target.public_id,
        )
        return OneTimePassword(
            one_time_password=one_time_password, one_time_password_expires_at=expires_at
        )

    async def _record_change(
        self,
        tenant: Tenant,
        actor: User,
        target: User,
        field: UserChangeField,
        *,
        old: str | None,
        new: str,
    ) -> None:
        await self.users.add_change(
            UserChange(
                tenant_id=tenant.tenant_id,
                actor_user_id=actor.user_id,
                target_user_id=target.user_id,
                changed_field=field.value,
                old_value=old,
                new_value=new,
                created_by=actor.user_id,
            )
        )

    async def _end_sessions(
        self, target: User, reason: RefreshSessionEndReason, now: datetime
    ) -> None:
        # rules/58: a changed authorization level or password ends every refresh session.
        await self.sessions.end_user_sessions(target.user_id, reason=reason.value, now=now)

    async def _target(self, public_id: UUID, tenant: Tenant) -> User:
        target = await self.users.get_in_tenant_for_update(public_id, tenant.tenant_id)
        if target is None:
            raise user_not_found()
        return target


def _summary(user: User, roles: tuple[str, ...]) -> UserSummary:
    return UserSummary(
        public_id=UUID(user.public_id),
        username=user.username,
        display_name=user.display_name,
        role=cast(AccountRoleValue | None, account_role(roles)),
        active=user.is_active,
        password_change_required=user.password_change_required,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )
