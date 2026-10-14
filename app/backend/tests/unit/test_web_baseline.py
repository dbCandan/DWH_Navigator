"""Security headers, the single error envelope and the cross-site request guard.

application-foundation/PRDs/001-user-accounts Requirement 10 (Basic header), 12 (token only in
the Authorization header; headers on event streams and downloads), 13, 14 and 15. These checks run
before any database work, so the real application answers them without PostgreSQL.
"""

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import Response, StreamingResponse
from httpx import ASGITransport, AsyncClient

from app.api.auth.endpoints import get_login_rate_limiter
from app.core.config import get_settings
from app.core.logging import JsonFormatter
from app.core.login_throttle import NAME_ADDRESS_MAX_FAILURES, LoginRateLimiter
from app.core.security import create_access_token
from app.main import create_application
from app.middleware.security_headers import SECURITY_HEADERS

pytestmark = pytest.mark.unit

PREFIX = get_settings().api_prefix
ORIGIN = get_settings().public_origin
TENANT_HEADER = get_settings().tenant_header
SECRET_MARKER = f"GIZLI-{uuid4().hex}"
EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "x-permitted-cross-domain-policies": "none",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-embedder-policy": "require-corp",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "cache-control": "no-store",
    "strict-transport-security": "max-age=31536000",
}


def _application() -> FastAPI:
    """The real application with three routes that only these tests register."""

    application = create_application()

    async def events() -> AsyncIterator[bytes]:
        yield b"data: one\n\n"
        await asyncio.sleep(0)
        yield b"data: two\n\n"

    async def stream() -> StreamingResponse:
        return StreamingResponse(events(), media_type="text/event-stream")

    async def download() -> Response:
        return Response(
            content=b"PK\x03\x04",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="rapor.xlsx"'},
        )

    async def crash() -> None:
        raise RuntimeError(f"SELECT secret FROM table -- {SECRET_MARKER} /etc/passwd")

    application.add_api_route(f"{PREFIX}/test-only/stream", stream, methods=["GET"])
    application.add_api_route(f"{PREFIX}/test-only/download", download, methods=["GET"])
    application.add_api_route(f"{PREFIX}/test-only/crash", crash, methods=["GET"])
    return application


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    application = _application()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def records() -> Iterator[list[logging.LogRecord]]:
    captured: list[logging.LogRecord] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = Handler()
    loggers = [logging.getLogger(name) for name in ("app.http", "app.security", "app.auth")]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    try:
        yield captured
    finally:
        for logger, level in zip(loggers, levels, strict=True):
            logger.removeHandler(handler)
            logger.setLevel(level)


def _tenant() -> dict[str, str]:
    return {TENANT_HEADER: str(uuid4())}


def _assert_security_headers(response: httpx.Response) -> None:
    headers = response.headers
    for name, value in EXPECTED_HEADERS.items():
        assert headers.get(name) == value, name
    assert "server" not in headers


def _assert_envelope(response: httpx.Response, code: str) -> None:
    body = response.json()
    assert set(body) == {"detail"}
    assert set(body["detail"]) == {"code", "message"}
    assert body["detail"]["code"] == code
    assert body["detail"]["message"]
    assert response.headers.get("x-request-id")


def test_the_header_list_is_the_accepted_one() -> None:
    assert {name.lower(): value for name, value in SECURITY_HEADERS} == EXPECTED_HEADERS


async def test_success_and_framework_errors_carry_headers_and_the_envelope(
    client: AsyncClient,
) -> None:
    alive = await client.get(f"{PREFIX}/liveness")
    assert alive.status_code == 200
    _assert_security_headers(alive)

    missing = await client.get(f"{PREFIX}/does-not-exist", headers=_tenant())
    assert missing.status_code == 404
    _assert_envelope(missing, "not_found")
    _assert_security_headers(missing)

    wrong_method = await client.get(f"{PREFIX}/auth/login")
    assert wrong_method.status_code == 405
    _assert_envelope(wrong_method, "method_not_allowed")
    assert wrong_method.headers["allow"] == "POST"
    _assert_security_headers(wrong_method)

    # A bearer request names its tenant; a request without session and tenant is a visitor's
    # (application-foundation 003-anonymous-visitor Decision 4) and the session endpoint says 401.
    no_tenant = await client.get(f"{PREFIX}/auth/me", headers={"Authorization": "Bearer x"})
    assert no_tenant.status_code == 400
    _assert_envelope(no_tenant, "tenant_header_required")
    _assert_security_headers(no_tenant)

    bad_tenant = await client.get(f"{PREFIX}/auth/me", headers={TENANT_HEADER: "not-a-uuid"})
    assert bad_tenant.status_code == 400
    _assert_envelope(bad_tenant, "tenant_invalid")


async def test_validation_errors_name_the_field_and_never_echo_the_value(
    client: AsyncClient,
) -> None:
    password = f"{SECRET_MARKER}{'x' * 129}"
    too_long = await client.post(
        f"{PREFIX}/auth/login", json={"username": "ad.soyad", "password": password}
    )
    assert too_long.status_code == 422
    _assert_envelope(too_long, "invalid_request")
    assert "body.password" in too_long.json()["detail"]["message"]
    assert SECRET_MARKER not in too_long.text
    _assert_security_headers(too_long)

    long_name = "a" * 65
    name = await client.post(
        f"{PREFIX}/auth/login", json={"username": long_name, "password": "x" * 20}
    )
    assert name.status_code == 422
    assert "body.username" in name.json()["detail"]["message"]
    assert long_name not in name.text

    # A JSON array instead of an object is the wrong body type (source finding 9).
    array = await client.post(f"{PREFIX}/auth/login", json=[SECRET_MARKER])
    assert array.status_code == 422
    assert SECRET_MARKER not in array.text

    broken = await client.post(
        f"{PREFIX}/auth/login",
        content=f'{{"username": "{SECRET_MARKER}", ',
        headers={"content-type": "application/json"},
    )
    assert broken.status_code == 422
    assert SECRET_MARKER not in broken.text


async def test_an_unexpected_error_is_a_fixed_500_and_only_its_type_is_logged(
    client: AsyncClient, records: list[logging.LogRecord]
) -> None:
    response = await client.get(
        f"{PREFIX}/test-only/crash", headers={**_tenant(), "x-request-id": "istek-500"}
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {"code": "internal_error", "message": "Sunucu hatası. Ayrıntı sunucu kaydında."}
    }
    assert response.headers["x-request-id"] == "istek-500"
    _assert_security_headers(response)
    for leaked in (SECRET_MARKER, "SELECT", "/etc/passwd", "RuntimeError", "Traceback"):
        assert leaked not in response.text
    (event,) = [record for record in records if record.getMessage() == "request.unhandled_error"]
    assert event.structured_fields["request_id"] == "istek-500"
    rendered = JsonFormatter().format(event)
    assert json.loads(rendered)["exception_type"] == "RuntimeError"
    assert SECRET_MARKER not in rendered


async def test_event_streams_and_downloads_carry_the_headers(client: AsyncClient) -> None:
    stream = await client.get(f"{PREFIX}/test-only/stream", headers=_tenant())
    assert stream.status_code == 200
    assert stream.text == "data: one\n\ndata: two\n\n"
    _assert_security_headers(stream)

    download = await client.get(f"{PREFIX}/test-only/download", headers=_tenant())
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment")
    _assert_security_headers(download)


async def test_basic_credentials_mean_nothing_and_no_response_asks_for_them(
    client: AsyncClient,
) -> None:
    # Built at run time so no encoded credential sits in the source for secret scanners to report.
    basic = base64.b64encode(b"user-placeholder:password-placeholder").decode()
    response = await client.get(
        f"{PREFIX}/auth/me", headers={**_tenant(), "Authorization": f"Basic {basic}"}
    )
    assert response.status_code == 401
    _assert_envelope(response, "not_authenticated")
    assert response.headers["www-authenticate"] == "Bearer"
    assert "basic" not in response.headers["www-authenticate"].lower()


async def test_the_access_token_counts_only_in_the_authorization_header(
    client: AsyncClient,
) -> None:
    tenant = uuid4()
    token = create_access_token(
        subject=uuid4(),
        username="ad.soyad",
        tenant_id=tenant,
        roles=["kullanici"],
        permissions=[],
        is_super_admin=False,
    )
    for query in ("access_token", "token", "authorization"):
        response = await client.get(
            f"{PREFIX}/auth/me", params={query: token}, headers={TENANT_HEADER: str(tenant)}
        )
        assert response.status_code == 401, query
    cookie = await client.get(
        f"{PREFIX}/auth/me",
        headers={TENANT_HEADER: str(tenant), "Cookie": f"access_token={token}"},
    )
    assert cookie.status_code == 401


async def test_rate_limited_login_answers_429_with_retry_after_before_any_password_check() -> None:
    limiter = LoginRateLimiter()
    for _ in range(NAME_ADDRESS_MAX_FAILURES):
        limiter.record_failure("ad.soyad", "127.0.0.1")
    application = _application()
    application.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    transport = ASGITransport(app=application, client=("127.0.0.1", 40000))
    async with AsyncClient(transport=transport, base_url="http://test") as limited:
        # The normalized name meets the counter; no database is reached before the refusal.
        response = await limited.post(
            f"{PREFIX}/auth/login", json={"username": " AD.SOYAD ", "password": "x" * 20}
        )
    assert response.status_code == 429
    _assert_envelope(response, "rate_limited")
    assert int(response.headers["retry-after"]) > 0
    _assert_security_headers(response)


# --- Requirement 13: cross-site requests -------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "expected"),
    (
        ({"Sec-Fetch-Site": "cross-site", "Origin": ORIGIN}, 403),
        ({"Sec-Fetch-Site": "same-site", "Origin": ORIGIN}, 403),
        ({"Sec-Fetch-Site": "same-origin", "Origin": ORIGIN}, 204),
        ({"Sec-Fetch-Site": "none", "Origin": ORIGIN}, 204),
        ({"Sec-Fetch-Site": "SAME-ORIGIN", "Origin": ORIGIN}, 204),
        ({"Origin": ORIGIN}, 204),
        ({"Origin": "https://evil.example.test"}, 403),
        ({"Origin": "null"}, 403),
        ({"Origin": ORIGIN + "/"}, 403),
        # The cookie endpoints require the exact Origin even when Sec-Fetch-Site is fine.
        ({"Sec-Fetch-Site": "same-origin"}, 403),
        ({}, 403),
    ),
)
async def test_cookie_endpoint_matrix(
    client: AsyncClient,
    records: list[logging.LogRecord],
    headers: dict[str, str],
    expected: int,
) -> None:
    response = await client.post(f"{PREFIX}/auth/logout", headers=headers)

    assert response.status_code == expected
    _assert_security_headers(response)
    if expected == 403:
        _assert_envelope(response, "cross_site_request")
        assert response.json()["detail"]["message"] == "Başka bir siteden gelen istek reddedildi."
        (event,) = [r for r in records if r.getMessage() == "security.cross_site_rejected"]
        fields = event.structured_fields
        assert fields["http_method"] == "POST"
        assert fields["http_route"] == f"{PREFIX}/auth/logout"
        assert fields["decided_by"] in {"sec_fetch_site", "origin"}
        assert "evil" not in json.dumps(fields)


@pytest.mark.parametrize(
    ("headers", "expected"),
    (
        # A non-browser client sends neither header; the endpoint itself still decides.
        ({}, 422),
        ({"Sec-Fetch-Site": "same-origin"}, 422),
        ({"Origin": ORIGIN}, 422),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Origin": "https://evil.example.test"}, 403),
        ({"Origin": "null"}, 403),
    ),
)
async def test_other_state_changing_requests_check_the_same_headers(
    client: AsyncClient, headers: dict[str, str], expected: int
) -> None:
    response = await client.post(f"{PREFIX}/auth/login", json={}, headers=headers)
    assert response.status_code == expected


async def test_the_guard_runs_before_tenant_and_session_checks(client: AsyncClient) -> None:
    target = f"{PREFIX}/admin/users/{uuid4()}/role"
    for method in ("PUT", "PATCH", "DELETE", "POST"):
        response = await client.request(
            method, target, json={"role": "yonetici"}, headers={"Sec-Fetch-Site": "cross-site"}
        )
        assert response.status_code == 403, method
        _assert_envelope(response, "cross_site_request")
    # Reading requests are never refused for their origin.
    read = await client.get(
        f"{PREFIX}/liveness", headers={"Sec-Fetch-Site": "cross-site", "Origin": "null"}
    )
    assert read.status_code == 200
