"""Login, password change, session refresh, logout and current-user service.

application-foundation/PRDs/001-user-accounts Requirement 1, 3, 4 and 6-9: local accounts only, a
15-minute access token and a rotating server-side refresh session. Login and password change share
the failed-attempt counters; the username never reaches a log line, only its keyed digest.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.login_throttle import LoginRateLimiter
from app.core.request_context import RequestContext
from app.core.security import (
    create_access_token,
    hash_password,
    login_name_digest,
    new_refresh_token,
    refresh_token_digest,
    verify_password,
)
from app.core.telemetry import record_login_attempt, record_password_change_attempt
from app.domain.accounts import account_role, normalize_username
from app.domain.models.refresh_session import RefreshSession, RefreshSessionEndReason
from app.domain.models.user import User
from app.domain.models.user_change import PasswordKind, UserChange, UserChangeField
from app.domain.password_policy import (
    PasswordPolicyReason,
    PasswordPolicyViolation,
    check_password_policy,
)
from app.infrastructure.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from app.infrastructure.repositories.user_repository import (
    AuthorizationSnapshot,
    UserRepository,
)
from app.schemas.auth.response import AccountRoleValue, AuthenticatedUser, LoginResponse

logger = logging.getLogger("app.auth")

_BEARER = {"WWW-Authenticate": "Bearer"}


def not_authenticated() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "not_authenticated",
        "Oturum açmanız gerekiyor.",
        headers=_BEARER,
    )


def invalid_credentials() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "invalid_credentials",
        "Kullanıcı adı veya parola hatalı.",
        headers=_BEARER,
    )


def user_inactive() -> ApplicationError:
    return ApplicationError(
        status.HTTP_403_FORBIDDEN,
        "user_inactive",
        "Hesabınız pasif; uygulama yöneticisine başvurun.",
    )


def one_time_password_expired() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "one_time_password_expired",
        "Tek kullanımlık parolanızın süresi doldu; uygulama yöneticisinden yenisini isteyin.",
        headers=_BEARER,
    )


def password_change_required() -> ApplicationError:
    return ApplicationError(
        status.HTTP_403_FORBIDDEN,
        "password_change_required",
        "Devam etmek için yeni bir parola belirleyin.",
    )


def rate_limited(retry_after: int) -> ApplicationError:
    return ApplicationError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "rate_limited",
        "Çok fazla hatalı deneme yapıldı. Lütfen biraz bekleyip yeniden deneyin.",
        headers={"Retry-After": str(retry_after)},
    )


def session_expired() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "session_expired",
        "Oturumunuzun süresi doldu. Lütfen yeniden giriş yapın.",
    )


def session_revoked() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "session_revoked",
        "Oturumunuz kapatıldı. Lütfen yeniden giriş yapın.",
    )


def tenant_unavailable() -> ApplicationError:
    return ApplicationError(
        status.HTTP_403_FORBIDDEN,
        "tenant_unavailable",
        "Hesabınızın bağlı olduğu kiracı kullanılamıyor.",
    )


class _CredentialFailure(Exception):
    """A refused password proof with its log reason class and client-facing error.

    Only a wrong password counts towards the failed-attempt limits; the other refusals already
    proved the password.
    """

    def __init__(self, reason: str, error: ApplicationError, *, counts: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.error = error
        self.counts = counts


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """A login, password change or refresh result: the body and the refresh cookie value."""

    response: LoginResponse
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings,
        rate_limiter: LoginRateLimiter,
    ) -> None:
        self.session = session
        self.settings = settings
        self.rate_limiter = rate_limiter
        self.users = UserRepository(session)
        self.sessions = RefreshSessionRepository(session)

    async def login(self, username: str, password: str, client_address: str) -> IssuedSession:
        name = normalize_username(username)
        name_digest = login_name_digest(name)
        self._refuse_when_limited(name, client_address, name_digest, record_login_attempt)
        user = await self.users.get_by_username(name)
        now = datetime.now(UTC)
        try:
            user = self._prove_password(user, password, now)
        except _CredentialFailure as failure:
            if failure.counts:
                self.rate_limiter.record_failure(name, client_address)
            log_event(logger, "auth.login.failed", reason=failure.reason, name_digest=name_digest)
            record_login_attempt(failure.reason)
            raise failure.error from None
        if user.password_change_required:
            log_event(logger, "auth.login.password_change_required", user_public_id=user.public_id)
            record_login_attempt("password_change_required")
            raise password_change_required()
        self.rate_limiter.record_success(name, client_address)
        user.last_login_at = now
        await self.sessions.purge_ended(now)
        issued = await self._issue(user, family_id=uuid4(), absolute_expires_at=None, now=now)
        log_event(logger, "auth.login.succeeded", user_public_id=user.public_id)
        record_login_attempt("succeeded")
        return issued

    async def change_password(
        self,
        username: str,
        current_password: str,
        new_password: str,
        client_address: str,
    ) -> IssuedSession:
        name = normalize_username(username)
        name_digest = login_name_digest(name)
        self._refuse_when_limited(name, client_address, name_digest, record_password_change_attempt)
        # The row lock queues concurrent changes of one account (API contract, rules/21).
        user = await self.users.get_by_username(name, for_update=True)
        now = datetime.now(UTC)
        try:
            user = self._prove_password(user, current_password, now)
        except _CredentialFailure as failure:
            if failure.counts:
                self.rate_limiter.record_failure(name, client_address)
            log_event(
                logger,
                "auth.password.change_failed",
                reason=failure.reason,
                name_digest=name_digest,
            )
            record_password_change_attempt(failure.reason)
            raise failure.error from None
        try:
            check_password_policy(
                new_password, username=user.username, display_name=user.display_name
            )
            if verify_password(new_password, user.password_hash):
                raise PasswordPolicyViolation(PasswordPolicyReason.REUSED)
        except PasswordPolicyViolation as violation:
            log_event(
                logger,
                "auth.password.change_failed",
                reason="password_policy",
                policy_reason=violation.reason.value,
                name_digest=name_digest,
            )
            record_password_change_attempt("password_policy")
            raise ApplicationError(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "password_policy", violation.message
            ) from None
        kind = "initial" if user.password_change_required else "voluntary"
        user.password_hash = hash_password(new_password)
        user.password_change_required = False
        user.one_time_password_expires_at = None
        user.password_changed_at = now
        user.last_login_at = now
        user.updated_by = user.user_id
        await self.sessions.end_user_sessions(
            user.user_id, reason=RefreshSessionEndReason.PASSWORD_CHANGED.value, now=now
        )
        await self.users.add_change(
            UserChange(
                tenant_id=user.home_tenant_id,
                actor_user_id=user.user_id,
                target_user_id=user.user_id,
                changed_field=UserChangeField.PASSWORD.value,
                old_value=None,
                new_value=PasswordKind.CHANGED.value,
                created_by=user.user_id,
            )
        )
        self.rate_limiter.record_success(name, client_address)
        await self.sessions.purge_ended(now)
        issued = await self._issue(user, family_id=uuid4(), absolute_expires_at=None, now=now)
        log_event(logger, "auth.password.changed", user_public_id=user.public_id, kind=kind)
        record_password_change_attempt("succeeded")
        return issued

    async def refresh(self, refresh_token: str | None) -> IssuedSession:
        if not refresh_token:
            raise session_expired()
        record = await self.sessions.get_by_digest_for_update(refresh_token_digest(refresh_token))
        if record is None:
            raise session_expired()
        now = datetime.now(UTC)
        if record.revoked_at is not None:
            if record.revoke_reason == RefreshSessionEndReason.ROTATED.value:
                await self.sessions.end_family(
                    record.family_id,
                    reason=RefreshSessionEndReason.REUSE_DETECTED.value,
                    now=now,
                )
                user = await self.users.get_by_id(record.user_id)
                # The revocation must survive the 401 below, which rolls the request back.
                await self.session.commit()
                log_event(
                    logger,
                    "auth.session.reuse_detected",
                    user_public_id=user.public_id if user is not None else None,
                    session_family=str(record.family_id),
                )
            raise session_revoked()
        if now >= record.idle_expires_at or now >= record.absolute_expires_at:
            raise session_expired()
        user = await self.users.get_by_id(record.user_id)
        if user is None or user.is_deleted or not user.is_active or user.password_change_required:
            await self.sessions.end_family(
                record.family_id,
                reason=RefreshSessionEndReason.AUTHORIZATION_CHANGED.value,
                now=now,
            )
            await self.session.commit()
            raise session_revoked()
        record.revoked_at = now
        record.revoke_reason = RefreshSessionEndReason.ROTATED.value
        record.last_used_at = now
        record.updated_by = user.user_id
        return await self._issue(
            user,
            family_id=record.family_id,
            absolute_expires_at=record.absolute_expires_at,
            now=now,
        )

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        record = await self.sessions.get_by_digest_for_update(refresh_token_digest(refresh_token))
        if record is None:
            return
        await self.sessions.end_family(
            record.family_id, reason=RefreshSessionEndReason.LOGOUT.value, now=datetime.now(UTC)
        )
        user = await self.users.get_by_id(record.user_id)
        log_event(
            logger,
            "auth.logout",
            user_public_id=user.public_id if user is not None else None,
        )

    async def current_user(self, context: RequestContext) -> AuthenticatedUser:
        if context.subject is None or context.tenant_id is None:
            raise not_authenticated()
        user = await self.users.get_active_by_public_id(context.subject)
        if user is None:
            raise not_authenticated()
        authorization = await self._authorization(user)
        response = authenticated_user(user, authorization)
        return response.model_copy(update={"tenant_id": context.tenant_id})

    def _refuse_when_limited(
        self,
        name: str,
        client_address: str,
        name_digest: str,
        record_attempt: Callable[[str], None],
    ) -> None:
        blocked = self.rate_limiter.blocked(name, client_address)
        if blocked is None:
            return
        limit, retry_after = blocked
        log_event(logger, "auth.login.rate_limited", name_digest=name_digest, limit=limit)
        record_attempt("rate_limited")
        raise rate_limited(retry_after)

    @staticmethod
    def _prove_password(user: User | None, password: str, now: datetime) -> User:
        # A missing account still spends one hash verification (verify_password).
        if not verify_password(password, user.password_hash if user is not None else None):
            raise _CredentialFailure("invalid_credentials", invalid_credentials(), counts=True)
        if user is None:  # pragma: no cover - verify_password refuses a missing account
            raise _CredentialFailure("invalid_credentials", invalid_credentials(), counts=True)
        if not user.is_active:
            raise _CredentialFailure("user_inactive", user_inactive(), counts=False)
        expires_at = user.one_time_password_expires_at
        if user.password_change_required and expires_at is not None and now >= expires_at:
            raise _CredentialFailure(
                "one_time_password_expired", one_time_password_expired(), counts=False
            )
        return user

    async def _authorization(self, user: User) -> AuthorizationSnapshot:
        try:
            return await self.users.authorization_for(user)
        except LookupError:
            raise tenant_unavailable() from None

    async def _issue(
        self,
        user: User,
        *,
        family_id: UUID,
        absolute_expires_at: datetime | None,
        now: datetime,
    ) -> IssuedSession:
        authorization = await self._authorization(user)
        absolute = absolute_expires_at or now + timedelta(
            hours=self.settings.refresh_session_absolute_hours
        )
        idle = min(now + timedelta(minutes=self.settings.refresh_session_idle_minutes), absolute)
        token = new_refresh_token()
        await self.sessions.add(
            RefreshSession(
                tenant_id=user.home_tenant_id,
                user_id=user.user_id,
                family_id=family_id,
                token_sha256=refresh_token_digest(token),
                idle_expires_at=idle,
                absolute_expires_at=absolute,
                created_by=user.user_id,
                updated_by=user.user_id,
            )
        )
        access_token = create_access_token(
            subject=UUID(user.public_id),
            username=user.username,
            tenant_id=UUID(authorization.tenant_public_id),
            roles=list(authorization.roles),
            permissions=list(authorization.permissions),
            is_super_admin=authorization.is_super_admin,
        )
        return IssuedSession(
            response=LoginResponse(
                access_token=access_token,
                expires_in=self.settings.access_token_expire_minutes * 60,
                user=authenticated_user(user, authorization),
            ),
            refresh_token=token,
            refresh_expires_at=absolute,
        )


def authenticated_user(user: User, authorization: AuthorizationSnapshot) -> AuthenticatedUser:
    return AuthenticatedUser(
        public_id=UUID(user.public_id),
        username=user.username,
        display_name=user.display_name,
        tenant_id=UUID(authorization.tenant_public_id),
        role=cast(AccountRoleValue | None, account_role(authorization.roles)),
        roles=list(authorization.roles),
        permissions=list(authorization.permissions),
        is_super_admin=authorization.is_super_admin,
    )
