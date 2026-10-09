"""The single API error envelope: {"detail": {"code": "...", "message": "..."}}.

application-foundation/PRDs/001-user-accounts Requirement 15. Layers raise ApplicationError with a
stable code and a safe Turkish message; the handlers here render it, render request validation
failures without echoing the submitted values and turn the framework's own 404 and 405 into the
same envelope. Messages never carry stack traces, SQL, tokens, paths or library names.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_ERROR_MESSAGE = "Sunucu hatası. Ayrıntı sunucu kaydında."
VALIDATION_ERROR_CODE = "invalid_request"

# A location part is shown only when it is a field name of the application's own schema; anything
# else (a key the client chose, a validator tag) becomes "?" so no submitted text is echoed.
_LOCATION_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_MAX_LOCATIONS = 10

# Status codes the framework itself raises, with their stable code and message.
_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    status.HTTP_400_BAD_REQUEST: ("bad_request", "İstek geçersiz."),
    status.HTTP_401_UNAUTHORIZED: ("not_authenticated", "Oturum açmanız gerekiyor."),
    status.HTTP_403_FORBIDDEN: ("forbidden", "Bu işlem için yetkiniz yok."),
    status.HTTP_404_NOT_FOUND: ("not_found", "İstenen adres bulunamadı."),
    status.HTTP_405_METHOD_NOT_ALLOWED: (
        "method_not_allowed",
        "Bu adres bu istek yöntemini desteklemiyor.",
    ),
    status.HTTP_413_CONTENT_TOO_LARGE: ("content_too_large", "İstek gövdesi çok büyük."),
}


class ApplicationError(Exception):
    """A request outcome with a stable HTTP status, error code and person-facing message."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = dict(headers or {})


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"detail": {"code": code, "message": message}}


def internal_error_response(headers: Mapping[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body(INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE),
        headers=dict(headers or {}) or None,
    )


def validation_locations(errors: Iterable[Mapping[str, Any]]) -> list[str]:
    """Dotted locations of the failing fields, never the values; unknown parts become "?"."""

    locations: list[str] = []
    for error in errors:
        raw = error.get("loc", ())
        parts = raw if isinstance(raw, Sequence) and not isinstance(raw, str) else (raw,)
        rendered = ".".join(
            (
                str(part)
                if isinstance(part, int)
                else part if isinstance(part, str) and _LOCATION_PART.fullmatch(part) else "?"
            )
            for part in parts
        )
        if rendered and rendered not in locations:
            locations.append(rendered)
        if len(locations) == _MAX_LOCATIONS:
            break
    return locations


def validation_message(locations: Sequence[str]) -> str:
    if not locations:
        return "İstek değerleri geçersiz."
    return "İstek değerleri geçersiz: " + ", ".join(locations) + "."


async def application_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApplicationError):  # pragma: no cover - registered for this type only
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
        headers=exc.headers or None,
    )


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registered for this type
        raise exc
    locations = validation_locations(exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_body(VALIDATION_ERROR_CODE, validation_message(locations)),
    )


async def http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover - registered for this type
        raise exc
    code, message = _HTTP_ERRORS.get(exc.status_code, ("http_error", "İstek işlenemedi."))
    # Keep protocol headers such as Allow on 405; a framework detail text never reaches the body.
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message),
        headers=dict(exc.headers) if exc.headers else None,
    )


def install_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(ApplicationError, application_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_error_handler)
