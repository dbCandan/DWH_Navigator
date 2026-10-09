"""OpenTelemetry signals of app.core.telemetry against in-memory providers.

application-foundation/PRDs/001-user-accounts Requirement 19 and its Gözlemlenebilirlik section:
the two counters with their bounded outcome labels, one server span per request named after the
route template, the request log line carrying the same trace identifier, and no request content.
"""

import json
import logging
from io import StringIO
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.trace import SpanKind, StatusCode

from app.core import telemetry
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.middleware.request_logging import RequestLoggingMiddleware
from tests.fakes.telemetry import TelemetryCapture

pytestmark = pytest.mark.unit

MARKER = f"GIZLI-{uuid4().hex}"


def test_no_endpoint_keeps_the_no_op_providers() -> None:
    settings = Settings(_env_file=None, otel_exporter_otlp_endpoint="")
    assert telemetry.configure_telemetry(settings) is None
    assert telemetry._signals is telemetry._NOOP
    # Every helper stays callable without a provider.
    telemetry.record_login_attempt("succeeded")
    telemetry.record_password_change_attempt("succeeded")
    with telemetry.http_server_span("GET") as span:
        span.complete("/x", 200)


def test_an_endpoint_installs_otlp_export_with_a_fixed_resource() -> None:
    settings = Settings(
        _env_file=None,
        environment="development",
        otel_exporter_otlp_endpoint="http://127.0.0.1:9",
        otel_service_name="dwhnavigator-test",
    )
    export = telemetry.configure_telemetry(settings)
    assert export is not None
    try:
        assert dict(export.tracer_provider.resource.attributes) == {
            "service.name": "dwhnavigator-test",
            "service.version": telemetry.SERVICE_VERSION,
            "deployment.environment.name": "local",
        }
    finally:
        export.shutdown()
    assert telemetry._signals is telemetry._NOOP


@pytest.mark.parametrize(
    ("value", "allowed", "expected"),
    (
        ("succeeded", telemetry.LOGIN_OUTCOMES, "succeeded"),
        ("password_change_required", telemetry.LOGIN_OUTCOMES, "password_change_required"),
        ("password_policy", telemetry.LOGIN_OUTCOMES, "other"),
        ("password_policy", telemetry.PASSWORD_CHANGE_OUTCOMES, "password_policy"),
        (f"ad.soyad {MARKER}", telemetry.LOGIN_OUTCOMES, "other"),
        (None, telemetry.PASSWORD_CHANGE_OUTCOMES, "other"),
    ),
)
def test_label_values_outside_their_set_become_other(
    value: object, allowed: frozenset[str], expected: str
) -> None:
    assert telemetry.bounded(value, allowed) == expected


def test_the_outcome_sets_are_the_accepted_ones() -> None:
    assert telemetry.LOGIN_OUTCOMES == {
        "succeeded",
        "invalid_credentials",
        "user_inactive",
        "one_time_password_expired",
        "password_change_required",
        "rate_limited",
    }
    assert telemetry.PASSWORD_CHANGE_OUTCOMES == {
        "succeeded",
        "invalid_credentials",
        "user_inactive",
        "one_time_password_expired",
        "password_policy",
        "rate_limited",
    }


def test_login_and_password_change_counters(telemetry_capture: TelemetryCapture) -> None:
    telemetry.record_login_attempt("succeeded")
    telemetry.record_login_attempt("rate_limited")
    telemetry.record_login_attempt(f"ad.soyad-{MARKER}")
    telemetry.record_password_change_attempt("password_policy")

    logins = "dwhnavigator_auth_login_attempts_total"
    changes = "dwhnavigator_auth_password_change_attempts_total"
    assert telemetry_capture.value(logins, outcome="succeeded") == 1
    assert telemetry_capture.value(logins, outcome="rate_limited") == 1
    assert telemetry_capture.value(logins, outcome="other") == 1
    assert telemetry_capture.value(changes, outcome="password_policy") == 1
    assert telemetry_capture.metric_names() == {logins, changes}
    assert MARKER not in telemetry_capture.everything()


def _application() -> FastAPI:
    application = FastAPI()
    application.add_middleware(RequestLoggingMiddleware)

    @application.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @application.get("/broken")
    async def broken() -> None:
        raise RuntimeError(MARKER)

    return application


async def test_server_spans_name_the_route_template_and_logs_carry_the_trace(
    telemetry_capture: TelemetryCapture,
) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    http_logger = logging.getLogger("app.http")
    http_logger.addHandler(handler)
    http_logger.setLevel(logging.INFO)
    try:
        transport = ASGITransport(app=_application(), raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get(f"/items/{MARKER}?q={MARKER}")).status_code == 200
            broken = await client.get("/broken", headers={"authorization": MARKER})
            assert broken.status_code == 500
    finally:
        http_logger.removeHandler(handler)

    ok_span = telemetry_capture.spans("GET /items/{item_id}")[0]
    assert ok_span.kind is SpanKind.SERVER
    assert dict(ok_span.attributes or {}) == {
        "http.request.method": "GET",
        "http.route": "/items/{item_id}",
        "http.response.status_code": 200,
    }
    failed_span = telemetry_capture.spans("GET /broken")[0]
    assert failed_span.status.status_code is StatusCode.ERROR
    assert failed_span.status.description is None
    assert MARKER not in telemetry_capture.everything()

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    completed = [line for line in lines if line["message"] == "request.completed"]
    assert completed[0]["trace_id"] == format(ok_span.context.trace_id, "032x")
    assert completed[0]["span_id"] == format(ok_span.context.span_id, "016x")


async def test_server_spans_and_logs_name_the_full_template_behind_router_prefixes(
    telemetry_capture: TelemetryCapture,
) -> None:
    items = APIRouter(prefix="/items")

    @items.get("/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    api = APIRouter(prefix="/api/v1")
    api.include_router(items)
    application = FastAPI()
    application.add_middleware(RequestLoggingMiddleware)
    application.include_router(api)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(f"/api/v1/items/{MARKER}")).status_code == 200
        assert (await client.get(f"/api/v1/missing/{MARKER}")).status_code == 404

    (span,) = telemetry_capture.spans("GET /api/v1/items/{item_id}")
    assert (span.attributes or {})["http.route"] == "/api/v1/items/{item_id}"
    (unmatched,) = telemetry_capture.spans("GET unmatched")
    assert (unmatched.attributes or {})["http.route"] == "unmatched"
    assert MARKER not in telemetry_capture.everything()


def test_logs_outside_a_span_carry_no_trace_fields() -> None:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "plain", None, None)
    payload = json.loads(JsonFormatter().format(record))
    assert "trace_id" not in payload
    assert "span_id" not in payload
