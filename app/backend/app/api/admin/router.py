"""Super-admin account administration: list, open, role, activation and password reset."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_super_admin
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.admin.users import (
    ActiveChange,
    OneTimePassword,
    RoleChange,
    UserCreated,
    UserCreateRequest,
    UserPage,
)
from app.schemas.errors import error_responses
from app.services.user_admin_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    UserAdminService,
)

_ERRORS = error_responses(
    {
        401: "not_authenticated: oturum yok",
        403: "forbidden: süper yönetici değil; cross_site_request: istek başka bir siteden geldi",
        422: "invalid_request: istek değerleri geçersiz",
    }
)

router = APIRouter(
    prefix="/admin/users",
    tags=["user-administration"],
    dependencies=[Depends(require_super_admin())],
    responses=_ERRORS,
)


def get_user_admin_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserAdminService:
    return UserAdminService(session, settings=settings)


Service = Annotated[UserAdminService, Depends(get_user_admin_service)]


@router.get("", response_model=UserPage)
async def list_users(
    context: CurrentContext,
    service: Service,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    q: Annotated[str | None, Query(max_length=128)] = None,
) -> UserPage:
    """List the accounts ordered by username; ``q`` searches username and display name."""

    return await service.list_users(context, page=page, size=size, query=q)


@router.post(
    "",
    response_model=UserCreated,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses({409: "username_taken: kullanıcı adı kullanılıyor"}),
)
async def create_user(
    body: UserCreateRequest, context: CurrentContext, service: Service
) -> UserCreated:
    """Open an account; the one-time password appears only in this response."""

    return await service.create_user(
        context, username=body.username, display_name=body.display_name, role_code=body.role
    )


@router.put(
    "/{public_id}/role",
    response_model=RoleChange,
    responses=error_responses(
        {404: "user_not_found", 409: "super_admin_protected: süper yönetici hesabı"}
    ),
)
async def set_role(
    public_id: UUID, body: RoleChange, context: CurrentContext, service: Service
) -> RoleChange:
    """Assign 'kullanici' or 'yonetici'; repeating the same value changes nothing."""

    return RoleChange(role=await service.set_role(context, public_id, body.role))


@router.put(
    "/{public_id}/active",
    response_model=ActiveChange,
    responses=error_responses(
        {
            404: "user_not_found",
            409: "own_account: kendi hesabı; super_admin_protected: süper yönetici hesabı",
        }
    ),
)
async def set_active(
    public_id: UUID, body: ActiveChange, context: CurrentContext, service: Service
) -> ActiveChange:
    """Deactivate or reactivate an account; repeating the same value changes nothing."""

    return ActiveChange(active=await service.set_active(context, public_id, body.active))


@router.post(
    "/{public_id}/password-reset",
    response_model=OneTimePassword,
    responses=error_responses(
        {404: "user_not_found", 409: "super_admin_protected: süper yönetici hesabı"}
    ),
)
async def reset_password(
    public_id: UUID, context: CurrentContext, service: Service
) -> OneTimePassword:
    """Issue a new one-time password; the previous password stops working at once."""

    return await service.reset_password(context, public_id)
