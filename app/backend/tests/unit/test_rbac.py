"""RBAC, role hierarchy and tenant-selection contract tests (user-accounts Requirement 10)."""

from uuid import uuid4

import pytest

from app.api.auth import dependencies
from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.core.security import TokenClaims
from app.middleware.tenant_context import tenant_is_allowed

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_permission_guard_allows_exact_permission() -> None:
    context = RequestContext(subject=uuid4(), permissions=frozenset({"invoice:read"}))
    assert await dependencies.require_permission("invoice:read")(context) is None


@pytest.mark.asyncio
async def test_permission_guard_denies_missing_permission() -> None:
    context = RequestContext(subject=uuid4())
    with pytest.raises(ApplicationError) as error:
        await dependencies.require_permission("invoice:read")(context)
    assert error.value.status_code == 403
    assert error.value.code == "forbidden"


@pytest.mark.asyncio
async def test_super_admin_bypasses_permissions_and_super_guard() -> None:
    context = RequestContext(subject=uuid4(), is_super_admin=True)
    assert await dependencies.require_permission("any:new-permission")(context) is None
    assert await dependencies.require_super_admin()(context) is None
    assert await dependencies.require_role("yonetici")(context) is None
    assert await dependencies.require_role("kullanici")(context) is None


@pytest.mark.asyncio
async def test_role_guard_lets_the_manager_do_what_the_user_does() -> None:
    manager = RequestContext(subject=uuid4(), roles=frozenset({"yonetici"}))
    user = RequestContext(subject=uuid4(), roles=frozenset({"kullanici"}))

    assert await dependencies.require_role("kullanici")(manager) is None
    assert await dependencies.require_role("yonetici")(manager) is None
    assert await dependencies.require_role("kullanici")(user) is None
    with pytest.raises(ApplicationError) as error:
        await dependencies.require_role("yonetici")(user)
    assert error.value.status_code == 403
    with pytest.raises(ApplicationError):
        await dependencies.require_super_admin()(manager)


def _claims(*, tenant_id: object, is_super_admin: bool) -> TokenClaims:
    return TokenClaims.model_validate(
        {
            "sub": str(uuid4()),
            "username": "person",
            "tenant_id": str(tenant_id),
            "roles": [],
            "permissions": [],
            "is_super_admin": is_super_admin,
            "exp": 4_102_444_800,
            "iat": 1_700_000_000,
            "iss": "test",
            "aud": "test-api",
        }
    )


def test_ordinary_user_cannot_switch_tenant() -> None:
    home = uuid4()
    assert tenant_is_allowed(_claims(tenant_id=home, is_super_admin=False), home)
    assert not tenant_is_allowed(_claims(tenant_id=home, is_super_admin=False), uuid4())


def test_super_admin_can_switch_tenant() -> None:
    assert tenant_is_allowed(_claims(tenant_id=uuid4(), is_super_admin=True), uuid4())
