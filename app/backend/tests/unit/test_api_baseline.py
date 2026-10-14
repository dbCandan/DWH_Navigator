"""Application construction, liveness, request logging, and OpenAPI tests."""

import json
import logging
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.logging import ApplicationJsonHandler, configure_logging
from app.main import app
from app.scripts.export_openapi import export_openapi

pytestmark = pytest.mark.unit


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_liveness(client: AsyncClient) -> None:
    prefix = get_settings().api_prefix
    assert (await client.get(f"{prefix}/liveness")).json() == {"status": "alive"}


def test_logging_configuration_is_idempotent_and_preserves_host_handlers() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    host_handler = logging.NullHandler()
    try:
        root.addHandler(host_handler)
        configure_logging("INFO")
        configure_logging("INFO")
        application_handlers = [
            handler for handler in root.handlers if isinstance(handler, ApplicationJsonHandler)
        ]
        assert host_handler in root.handlers
        assert len(application_handlers) == 1
        assert application_handlers[0].stream is sys.stdout
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


async def test_request_logging_is_correlated_and_excludes_request_data(
    client: AsyncClient,
) -> None:
    records: list[logging.LogRecord] = []

    class RecordHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    request_logger = logging.getLogger("app.http")
    original_level = request_logger.level
    handler = RecordHandler()
    request_logger.addHandler(handler)
    request_logger.setLevel(logging.INFO)
    prefix = get_settings().api_prefix
    try:
        response = await client.get(
            f"{prefix}/liveness?secret=must-not-be-logged",
            headers={"x-request-id": "test-request-123", "authorization": "Bearer hidden"},
        )
    finally:
        request_logger.removeHandler(handler)
        request_logger.setLevel(original_level)

    assert response.headers["x-request-id"] == "test-request-123"
    record = next(item for item in records if item.message == "request.completed")
    fields = record.structured_fields
    assert fields["request_id"] == "test-request-123"
    assert fields["http_route"] == f"{prefix}/liveness"
    serialized = json.dumps(fields)
    assert "must-not-be-logged" not in serialized
    assert "Bearer hidden" not in serialized


async def test_a_bearer_request_requires_the_tenant_header(client: AsyncClient) -> None:
    prefix = get_settings().api_prefix
    response = await client.get(f"{prefix}/auth/me", headers={"Authorization": "Bearer x"})
    assert response.status_code == 400
    assert response.json() == {
        "detail": {"code": "tenant_header_required", "message": "Etkin kiracı başlığı gerekli."}
    }
    # Without a session and a tenant the request is a visitor's; the session endpoint says 401
    # (application-foundation 003-anonymous-visitor Decision 3, 4).
    visitor = await client.get(f"{prefix}/auth/me")
    assert visitor.status_code == 401
    assert visitor.json()["detail"]["code"] == "not_authenticated"


async def test_me_authentication_error_has_bearer_challenge(client: AsyncClient) -> None:
    settings = get_settings()
    response = await client.get(
        f"{settings.api_prefix}/auth/me",
        headers={settings.tenant_header: str(uuid4())},
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["detail"]["code"] == "not_authenticated"


async def test_openapi_contains_frontend_auth_contract(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    prefix = get_settings().api_prefix
    assert f"{prefix}/auth/login" in paths
    assert f"{prefix}/auth/me" in paths
    assert f"{prefix}/readiness" in paths
    login_schema = schema["components"]["schemas"]["LoginRequest"]
    assert login_schema["required"] == ["username", "password"]


def test_openapi_export_is_offline_and_deterministic(tmp_path: Path) -> None:
    output = tmp_path / "app-api.yaml"
    schema = export_openapi(output)
    assert output.is_file()
    assert f"{get_settings().api_prefix}/auth/login" in schema["paths"]
