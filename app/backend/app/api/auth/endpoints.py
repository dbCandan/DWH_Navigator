"""Login, password change, session refresh, logout and current-user endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext
from app.core.client_address import resolve_client_address
from app.core.config import Settings, get_settings
from app.core.login_throttle import LoginRateLimiter, login_rate_limiter
from app.db.session import get_db
from app.schemas.auth.request import LoginRequest, PasswordChangeRequest
from app.schemas.auth.response import AuthenticatedUser, LoginResponse
from app.schemas.errors import error_responses
from app.services.auth_service import AuthService, IssuedSession

router = APIRouter()

REFRESH_COOKIE_NAME = "dwhnavigator_refresh"


def get_login_rate_limiter() -> LoginRateLimiter:
    return login_rate_limiter


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)],
) -> AuthService:
    return AuthService(session, settings=settings, rate_limiter=rate_limiter)


Service = Annotated[AuthService, Depends(get_auth_service)]
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)]


def _client_address(request: Request, settings: Settings) -> str:
    return resolve_client_address(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        settings.trusted_proxy_networks,
    )


def _cookie_path(settings: Settings) -> str:
    return f"{settings.api_prefix}/auth"


def _set_refresh_cookie(response: Response, issued: IssuedSession, settings: Settings) -> None:
    max_age = int((issued.refresh_expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        issued.refresh_token,
        max_age=max(max_age, 0),
        path=_cookie_path(settings),
        secure=True,
        httponly=True,
        samesite="strict",
    )


_SAME_ORIGIN = "cross_site_request: istek başka bir siteden geldi"
_RATE_LIMITED = "rate_limited: çok fazla hatalı deneme; Retry-After başlığı bekleme süresidir"
_INVALID = "invalid_request: istek değerleri geçersiz"


@router.post(
    "/login",
    response_model=LoginResponse,
    responses=error_responses(
        {
            401: "invalid_credentials, one_time_password_expired",
            403: f"user_inactive, password_change_required, {_SAME_ORIGIN}",
            422: _INVALID,
            429: _RATE_LIMITED,
        }
    ),
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    service: Service,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """Check username and password; issue an access token and a refresh cookie."""

    issued = await service.login(
        body.username, body.password.get_secret_value(), _client_address(request, settings)
    )
    _set_refresh_cookie(response, issued, settings)
    return issued.response


@router.post(
    "/password",
    response_model=LoginResponse,
    responses=error_responses(
        {
            401: "invalid_credentials, one_time_password_expired",
            403: f"user_inactive, {_SAME_ORIGIN}",
            422: f"password_policy: yeni parola kurala uymuyor; {_INVALID}",
            429: _RATE_LIMITED,
        }
    ),
)
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    response: Response,
    service: Service,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """Replace the current or one-time password and open a session, like a login."""

    issued = await service.change_password(
        body.username,
        body.current_password.get_secret_value(),
        body.new_password.get_secret_value(),
        _client_address(request, settings),
    )
    _set_refresh_cookie(response, issued, settings)
    return issued.response


@router.post(
    "/refresh",
    response_model=LoginResponse,
    responses=error_responses(
        {401: "session_expired, session_revoked", 403: _SAME_ORIGIN, 422: _INVALID}
    ),
)
async def refresh(
    response: Response,
    service: Service,
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: RefreshCookie = None,
) -> LoginResponse:
    """Rotate the refresh cookie and return a new access token with the current role."""

    issued = await service.refresh(refresh_token)
    _set_refresh_cookie(response, issued, settings)
    return issued.response


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses({403: _SAME_ORIGIN, 422: _INVALID}),
)
async def logout(
    service: Service,
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: RefreshCookie = None,
) -> Response:
    """End the refresh session on the server and delete the cookie; works without a token."""

    await service.logout(refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=_cookie_path(settings),
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return response


@router.get(
    "/me",
    response_model=AuthenticatedUser,
    responses=error_responses({401: "not_authenticated"}),
)
async def me(context: CurrentContext, service: Service) -> AuthenticatedUser:
    """Return the signed-in account with its display name and current role."""

    return await service.current_user(context)
