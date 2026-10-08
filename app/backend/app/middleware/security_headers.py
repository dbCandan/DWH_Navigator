"""Security headers on every response and the last line of the single error envelope.

application-foundation/PRDs/001-user-accounts Requirement 14 and 15. This pure ASGI middleware is
the outermost application layer: it adds the headers to every response the application sends,
errors, event streams and file downloads included, and turns an exception no inner layer handled
into the fixed 500 envelope with the request identifier. The exception is logged with its type and
the request identifier only; its text, which can carry SQL, a path or an address, is never written.
"""

import logging
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import internal_error_response

logger = logging.getLogger("app.http")

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("X-Permitted-Cross-Domain-Policies", "none"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Embedder-Policy", "require-corp"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
    ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"),
    ("Cache-Control", "no-store"),
    ("Strict-Transport-Security", "max-age=31536000"),
)


def _request_id(scope: Scope) -> str:
    state = scope.get("state")
    value = state.get("request_id") if isinstance(state, dict) else None
    return value if isinstance(value, str) and value else str(uuid4())


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    headers[name] = value
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            if started:
                # A streamed response already sent its status; the connection ends with the error.
                raise
            request_id = _request_id(scope)
            logger.exception(
                "request.unhandled_error",
                extra={
                    "structured_fields": {
                        "event": "request.unhandled_error",
                        "request_id": request_id,
                    }
                },
            )
            response = internal_error_response({"x-request-id": request_id})
            await response(scope, receive, send_with_headers)
