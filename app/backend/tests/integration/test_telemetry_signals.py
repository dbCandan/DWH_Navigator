"""OpenTelemetry signals of real login and password-change requests, captured in memory.

application-foundation/PRDs/001-user-accounts Requirement 19 and its Gözlemlenebilirlik section:
the two counters with their bounded outcome labels, one server span per request named after the
route template, no username, password or token in any span or metric, start-up refusal of OTEL_
process variables and no export without a collector address.
"""

import pytest
from pydantic import ValidationError

from app.core import telemetry
from app.core.config import Settings
from app.core.login_throttle import NAME_ADDRESS_MAX_FAILURES
from tests.fakes.telemetry import TelemetryCapture
from tests.integration.conftest import AuthHarness, new_password

pytestmark = pytest.mark.integration

LOGINS = "dwhnavigator_auth_login_attempts_total"
CHANGES = "dwhnavigator_auth_password_change_attempts_total"


async def test_login_outcomes_are_counted_without_names_or_passwords(
    auth: AuthHarness, telemetry_capture: TelemetryCapture
) -> None:
    admin = await auth.super_admin()
    opened = await auth.open_account(admin, "kullanici")
    first = await auth.login(opened.username, opened.one_time_password)
    assert first.status_code == 403
    account = await auth.activate(opened.username, opened.one_time_password)
    wrong_password = new_password()
    for _ in range(NAME_ADDRESS_MAX_FAILURES):
        assert (await auth.login(account.username, wrong_password)).status_code == 401
    assert (await auth.login(account.username, account.password)).status_code == 429
    auth.limiter.clear()
    succeeded = await auth.login(account.username, account.password)
    assert succeeded.status_code == 200

    capture = telemetry_capture
    assert capture.value(LOGINS, outcome="succeeded") == 1
    assert capture.value(LOGINS, outcome="password_change_required") == 1
    assert capture.value(LOGINS, outcome="invalid_credentials") == NAME_ADDRESS_MAX_FAILURES
    assert capture.value(LOGINS, outcome="rate_limited") == 1
    # The super admin's and the account's first passwords went through the password endpoint.
    assert capture.value(CHANGES, outcome="succeeded") == 2
    login_route = f"{auth.prefix}/auth/login"
    login_spans = capture.spans(f"POST {login_route}")
    assert len(login_spans) == NAME_ADDRESS_MAX_FAILURES + 3
    assert {(span.attributes or {}).get("http.route") for span in login_spans} == {login_route}
    assert {(span.attributes or {}).get("http.response.status_code") for span in login_spans} == {
        200,
        401,
        403,
        429,
    }
    everything = capture.everything()
    for secret in (
        account.username,
        admin.username,
        account.password,
        wrong_password,
        opened.one_time_password,
        succeeded.json()["access_token"],
    ):
        assert secret not in everything


async def test_password_change_outcomes_are_counted(
    auth: AuthHarness, telemetry_capture: TelemetryCapture
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    assert (
        await auth.change_password(account.username, account.password, "kisa")
    ).status_code == 422
    assert (
        await auth.change_password(account.username, new_password(), new_password())
    ).status_code == 401
    assert (
        await auth.change_password(account.username, account.password, new_password())
    ).status_code == 200

    assert telemetry_capture.value(CHANGES, outcome="password_policy") == 1
    assert telemetry_capture.value(CHANGES, outcome="invalid_credentials") == 1
    assert telemetry_capture.value(CHANGES, outcome="succeeded") == 3
    assert telemetry_capture.metric_names() <= {LOGINS, CHANGES}
    route = f"{auth.prefix}/auth/password"
    assert len(telemetry_capture.spans(f"POST {route}")) == 5
    assert account.password not in telemetry_capture.everything()


def test_otel_process_variables_stop_start_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://elsewhere.example.test:4317")
    with pytest.raises(ValidationError, match="OTEL_EXPORTER_OTLP_ENDPOINT"):
        Settings(_env_file=None)


def test_an_empty_collector_address_exports_nothing() -> None:
    settings = Settings(_env_file=None, otel_exporter_otlp_endpoint="")
    assert telemetry.configure_telemetry(settings) is None
    assert telemetry._signals is telemetry._NOOP
