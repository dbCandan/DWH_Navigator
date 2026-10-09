"""Refuse state-changing requests that another site's page sent (CSRF).

application-foundation/PRDs/001-user-accounts Requirement 13 and Decision 12. Before any tenant or
session check, every POST, PUT, PATCH and DELETE is inspected: a ``Sec-Fetch-Site`` header must be
``same-origin`` or ``none``; without it, an ``Origin`` header must equal the configured application
origin exactly (``null`` included in the refusals). A request without either header comes from a
non-browser client and passes; the protected endpoint still requires a session. The two endpoints
whose identity is the refresh cookie additionally require that exact ``Origin``.
"""

import logging
from collections.abc import Collection

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.errors import error_body
from app.core.logging import log_event
from app.middleware.request_logging import match_route_template

logger = logging.getLogger("app.security")

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ALLOWED_FETCH_SITES = frozenset({"same-origin", "none"})
CROSS_SITE_STATUS = 403
CROSS_SITE_CODE = "cross_site_request"
CROSS_SITE_MESSAGE = "Başka bir siteden gelen istek reddedildi."


def cross_site_refusal(
    method: str,
    path: str,
    headers: Headers,
    *,
    public_origin: str,
    cookie_paths: Collection[str],
) -> str | None:
    """The header that decided a refusal (``sec_fetch_site`` or ``origin``), or None to pass."""

    if method.upper() not in STATE_CHANGING_METHODS:
        return None
    origin = (headers.get("origin") or "").strip()
    fetch_site = (headers.get("sec-fetch-site") or "").strip().lower()
    if fetch_site:
        if fetch_site not in ALLOWED_FETCH_SITES:
            return "sec_fetch_site"
    elif origin and origin != public_origin:
        return "origin"
    if path in cookie_paths and origin != public_origin:
        return "origin"
    return None


class CrossSiteRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        settings = get_settings()
        self.public_origin = settings.public_origin
        self.cookie_paths = frozenset(
            {f"{settings.api_prefix}/auth/refresh", f"{settings.api_prefix}/auth/logout"}
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", ""))
        decided_by = cross_site_refusal(
            method,
            str(scope.get("path", "")),
            Headers(scope=scope),
            public_origin=self.public_origin,
            cookie_paths=self.cookie_paths,
        )
        if decided_by is None:
            await self.app(scope, receive, send)
            return
        log_event(
            logger,
            "security.cross_site_rejected",
            http_method=method,
            http_route=match_route_template(scope.get("app"), scope),
            decided_by=decided_by,
        )
        response = JSONResponse(
            status_code=CROSS_SITE_STATUS, content=error_body(CROSS_SITE_CODE, CROSS_SITE_MESSAGE)
        )
        await response(scope, receive, send)
