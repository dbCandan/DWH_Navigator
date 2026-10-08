"""Resolve the active tenant and the acting account of an authenticated request."""

from fastapi import status

from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.domain.accounts import role_satisfies
from app.domain.models.tenant import Tenant
from app.domain.models.user import User
from app.infrastructure.repositories.user_repository import UserRepository
from app.services.auth_service import not_authenticated


def forbidden() -> ApplicationError:
    return ApplicationError(status.HTTP_403_FORBIDDEN, "forbidden", "Bu işlem için yetkiniz yok.")


async def active_tenant(users: UserRepository, context: RequestContext) -> Tenant:
    """The tenant selected by the request header, already matched against the token."""

    if context.tenant_id is None:
        raise not_authenticated()
    tenant = await users.get_tenant_by_public_id(context.tenant_id)
    if tenant is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "tenant_not_found", "Kiracı bulunamadı.")
    return tenant


async def acting_user(users: UserRepository, context: RequestContext) -> User:
    """The caller re-read from the database; an inactive or missing account is not signed in."""

    if context.subject is None:
        raise not_authenticated()
    actor = await users.get_active_by_public_id(context.subject)
    if actor is None:
        raise not_authenticated()
    return actor


async def acting_user_with_role(
    users: UserRepository, context: RequestContext, required_role: str
) -> User:
    """The caller with ``required_role`` re-read from the database, not taken from the token.

    application-foundation 001 Decision 20: the account-management endpoints and the state-changing
    administration endpoints check the current role and status on every request.
    """

    actor = await acting_user(users, context)
    if not role_satisfies(await users.role_codes(actor), required_role):
        raise forbidden()
    return actor
