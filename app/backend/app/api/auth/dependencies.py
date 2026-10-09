"""FastAPI authentication, role, permission and super-admin guards.

application-foundation/PRDs/001-user-accounts Requirement 10: only a verified bearer access token
authenticates; an ``Authorization: Basic`` header carries no meaning and no response asks for it.
The super admin passes every role and permission check centrally.
"""

from typing import Annotated

from fastapi import Depends, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.middleware.tenant_context import get_request_context_dependency

bearer_scheme = HTTPBearer(auto_error=False)


def _not_authenticated() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "not_authenticated",
        "Oturum açmanız gerekiyor.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden() -> ApplicationError:
    return ApplicationError(status.HTTP_403_FORBIDDEN, "forbidden", "Bu işlem için yetkiniz yok.")


async def get_current_context(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    context: Annotated[RequestContext, Depends(get_request_context_dependency)],
) -> RequestContext:
    if credentials is None or not context.is_authenticated:
        raise _not_authenticated()
    return context


CurrentContext = Annotated[RequestContext, Depends(get_current_context)]


class PermissionChecker:
    def __init__(self, permission: str) -> None:
        self.permission = permission

    async def __call__(self, context: CurrentContext) -> None:
        if not context.has_permission(self.permission):
            raise _forbidden()


def require_permission(permission: str) -> PermissionChecker:
    return PermissionChecker(permission)


class RoleChecker:
    """Allow ``role`` or a role above it; the super admin passes every role check."""

    def __init__(self, role: str) -> None:
        self.role = role

    async def __call__(self, context: CurrentContext) -> None:
        if not context.has_role(self.role):
            raise _forbidden()


def require_role(role: str) -> RoleChecker:
    return RoleChecker(role)


class SuperAdminChecker:
    async def __call__(self, context: CurrentContext) -> None:
        if not context.is_super_admin:
            raise _forbidden()


def require_super_admin() -> SuperAdminChecker:
    return SuperAdminChecker()
