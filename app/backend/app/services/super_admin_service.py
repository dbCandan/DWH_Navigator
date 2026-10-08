"""The super admin: one creation path for the operator command and the backend start.

application-foundation/PRDs/001-user-accounts Requirement 17 and 18, Decision 18 and 21. The
operator command ``python -m app.scripts.create_super_admin`` creates the account or resets its
password, activation and super admin assignment. When the start-up password is configured, the
backend start creates the named account once and never changes an account that already carries
the name, so a password the super admin chose survives every redeploy. Both paths leave the
password as a one-time password without expiry: the account sets its own password at its first
login. Neither path logs, prints or traces the password or its hash.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import log_event
from app.core.security import hash_password, verify_password
from app.domain.accounts import (
    SUPER_ADMIN_DISPLAY_NAME,
    SUPER_ADMIN_ROLE,
    InvalidUsername,
    application_role_of,
    validate_new_username,
)
from app.domain.models.refresh_session import RefreshSessionEndReason
from app.domain.models.role import UserRole
from app.domain.models.tenant import PLATFORM_TENANT_CODE
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
from app.infrastructure.repositories.user_repository import UserRepository

logger = logging.getLogger("app.auth")

RejectionReason = Literal["invalid_username", "password_policy", "identity_conflict"]
SessionFactory = Callable[[], AsyncSession]

BOOTSTRAP_FIRST_RETRY_SECONDS = 2.0
BOOTSTRAP_MAX_RETRY_SECONDS = 60.0


class SuperAdminRejected(ValueError):
    """The name or password cannot become the super admin; the message carries no secret."""

    def __init__(self, reason: RejectionReason, message: str) -> None:
        super().__init__(message)
        self.reason: RejectionReason = reason


@dataclass(frozen=True, slots=True)
class SuperAdminResult:
    user_public_id: UUID
    tenant_public_id: UUID
    created: bool
    is_super_admin: bool


class BootstrapOutcome(StrEnum):
    """Result of the start-up creation; the ``outcome`` field of ``auth.super_admin.bootstrap``."""

    NOT_CONFIGURED = "not_configured"
    CREATED = "created"
    EXISTS = "exists"
    REJECTED = "rejected"


async def ensure_super_admin(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    email: str = "",
    reset_existing: bool = True,
) -> SuperAdminResult:
    """Create the super admin, or reset it when ``reset_existing``; owns and ends the transaction.

    Without ``reset_existing`` an account that already carries the name is left exactly as it is;
    its password, role and status are neither checked nor changed.
    """

    try:
        name = validate_new_username(username)
    except InvalidUsername as exc:
        raise SuperAdminRejected("invalid_username", str(exc)) from None
    normalized_email = email.strip().lower() or None

    users = UserRepository(session)
    # Every creation path serializes here, so a backend start and the operator command running
    # together see the account the first one created instead of racing on the unique name.
    await users.lock_super_admin_creation()
    user = await users.get_by_username(name, for_update=True)
    if user is not None and not reset_existing:
        roles = await users.role_codes(user)
        tenant_public_id = await users.get_tenant_public_id(user.home_tenant_id)
        result = SuperAdminResult(
            user_public_id=UUID(user.public_id),
            tenant_public_id=UUID(tenant_public_id),
            created=False,
            is_super_admin=SUPER_ADMIN_ROLE in roles,
        )
        await session.rollback()
        return result

    try:
        check_password_policy(
            password,
            username=name,
            display_name=user.display_name if user is not None else SUPER_ADMIN_DISPLAY_NAME,
        )
        if user is not None and verify_password(password, user.password_hash):
            raise PasswordPolicyViolation(PasswordPolicyReason.REUSED)
    except PasswordPolicyViolation as violation:
        # The reason names the rule, never the password.
        raise SuperAdminRejected("password_policy", violation.reason.value) from None
    if normalized_email is not None:
        owner = await users.find_email_owner(
            normalized_email, excluding_user_id=user.user_id if user is not None else None
        )
        if owner is not None:
            raise SuperAdminRejected("identity_conflict", "email is assigned to another account")

    tenant = await users.get_tenant_by_code(PLATFORM_TENANT_CODE)
    role = await users.get_role(SUPER_ADMIN_ROLE)
    if tenant is None or role is None:
        raise RuntimeError("the platform tenant and roles are missing; run Alembic migrations")
    password_hash = hash_password(password)
    now = datetime.now(UTC)
    changes: list[tuple[UserChangeField, str | None, str]] = []

    created = user is None
    if user is None:
        user = await users.add_user(
            User(
                home_tenant_id=tenant.tenant_id,
                username=name,
                email=normalized_email,
                display_name=SUPER_ADMIN_DISPLAY_NAME,
                password_hash=password_hash,
                # Decision 21: the start-up password works once and never expires.
                password_change_required=True,
                one_time_password_expires_at=None,
                is_active=True,
            )
        )
        changes.append((UserChangeField.ACCOUNT, None, SUPER_ADMIN_ROLE))
    else:
        user.password_hash = password_hash
        user.password_change_required = True
        user.one_time_password_expires_at = None
        if normalized_email is not None:
            user.email = normalized_email
        changes.append((UserChangeField.PASSWORD, None, PasswordKind.RESET.value))
        if not user.is_active:
            user.is_active = True
            changes.append((UserChangeField.ACTIVE, "false", "true"))

    assignment = await users.get_role_assignment(
        user_id=user.user_id, role_id=role.role_id, tenant_id=tenant.tenant_id
    )
    if assignment is None or assignment.is_deleted:
        if not created:
            previous = application_role_of(await users.role_codes(user))
            changes.append((UserChangeField.ROLE, previous, SUPER_ADMIN_ROLE))
        if assignment is None:
            await users.add_role_assignment(
                UserRole(
                    user_id=user.user_id,
                    role_id=role.role_id,
                    tenant_id=tenant.tenant_id,
                    created_by=user.user_id,
                    updated_by=user.user_id,
                )
            )
        else:
            assignment.is_deleted = False
            assignment.deleted_at = None
            assignment.deleted_by = None
            assignment.updated_by = user.user_id

    # No person made these changes; the account itself is recorded as the actor.
    for field, old, new in changes:
        await users.add_change(
            UserChange(
                tenant_id=tenant.tenant_id,
                actor_user_id=user.user_id,
                target_user_id=user.user_id,
                changed_field=field.value,
                old_value=old,
                new_value=new,
                created_by=user.user_id,
            )
        )
    if not created:
        await RefreshSessionRepository(session).end_user_sessions(
            user.user_id, reason=RefreshSessionEndReason.PASSWORD_CHANGED.value, now=now
        )
    user.created_by = user.created_by or user.user_id
    user.updated_by = user.user_id
    await session.commit()
    return SuperAdminResult(
        user_public_id=UUID(user.public_id),
        tenant_public_id=UUID(tenant.public_id),
        created=created,
        is_super_admin=True,
    )


async def bootstrap_super_admin(
    session_factory: SessionFactory, settings: Settings
) -> BootstrapOutcome:
    """One start-up attempt; database errors propagate so the caller can retry."""

    password = settings.bootstrap_super_admin_password
    if password is None:
        # Requirement 17: without a start-up password nothing happens and no database is reached.
        log_event(
            logger, "auth.super_admin.bootstrap", outcome=BootstrapOutcome.NOT_CONFIGURED.value
        )
        return BootstrapOutcome.NOT_CONFIGURED
    try:
        async with session_factory() as session:
            result = await ensure_super_admin(
                session,
                username=settings.bootstrap_super_admin_username,
                password=password.get_secret_value(),
                email=settings.bootstrap_super_admin_email,
                reset_existing=False,
            )
    except SuperAdminRejected as rejected:
        log_event(
            logger,
            "auth.super_admin.bootstrap",
            outcome=BootstrapOutcome.REJECTED.value,
            reason=rejected.reason,
        )
        return BootstrapOutcome.REJECTED
    outcome = BootstrapOutcome.CREATED if result.created else BootstrapOutcome.EXISTS
    log_event(
        logger,
        "auth.super_admin.bootstrap",
        outcome=outcome.value,
        user_public_id=str(result.user_public_id),
        super_admin=result.is_super_admin,
    )
    return outcome


async def run_super_admin_bootstrap(
    session_factory: SessionFactory,
    settings: Settings,
    *,
    first_retry_seconds: float = BOOTSTRAP_FIRST_RETRY_SECONDS,
    max_retry_seconds: float = BOOTSTRAP_MAX_RETRY_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> BootstrapOutcome:
    """Background task of the backend start: retry until the database and schema answer.

    On a first installation the migration job may still be creating the schema while the backend
    starts; the start neither waits for this task nor fails because of it.
    """

    delay = first_retry_seconds
    attempt = 1
    while True:
        try:
            return await bootstrap_super_admin(session_factory, settings)
        except Exception as error:  # noqa: BLE001 - reported with its type only
            # The message of a database error may quote statement parameters; only the type is
            # written.
            log_event(
                logger,
                "auth.super_admin.bootstrap_retry",
                attempt=attempt,
                error_type=type(error).__name__,
                retry_in_seconds=round(delay),
            )
        await sleep(delay)
        delay = min(delay * 2, max_retry_seconds)
        attempt += 1
