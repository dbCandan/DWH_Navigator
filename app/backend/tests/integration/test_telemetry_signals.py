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


def test_term_list_and_vote_signals_keep_their_label_sets(
    telemetry_capture: TelemetryCapture,
) -> None:
    """data-dictionary 005-list-search and 006-answer-feedback Gözlemlenebilirlik: the metric
    names and their fixed label sets; a value outside a set is ``other``."""

    telemetry.record_term_list_started()
    for status in ("completed", "cancelled", "interrupted", "running"):
        telemetry.record_term_list_finished(status)
    for outcome in ("analyst", "reused", "unavailable", "error", "stopped"):
        telemetry.record_term_list_term(outcome)
    for reason in ("term_list_running", "upload_too_large", "dosya.xlsx"):
        telemetry.record_term_list_upload_rejected(reason)
    telemetry.term_lists_running_changed(1)
    telemetry.term_lists_running_changed(-1)
    for kind in ("list", "item", "liste"):
        telemetry.record_term_list_report(kind)
    for scope, vote in (("table", "up"), ("answer", "down"), ("object", "maybe")):
        telemetry.record_feedback_vote(scope, vote)
    telemetry.record_feedback_saved_answers_forgotten(2)
    telemetry.record_feedback_saved_answers_forgotten(0)
    telemetry.record_feedback_apply_failure()

    capture = telemetry_capture
    assert {
        "dwhnavigator_term_lists_started_total",
        "dwhnavigator_term_lists_finished_total",
        "dwhnavigator_term_list_terms_total",
        "dwhnavigator_term_list_uploads_rejected_total",
        "dwhnavigator_term_lists_running",
        "dwhnavigator_term_list_reports_total",
        "dwhnavigator_feedback_votes_total",
        "dwhnavigator_feedback_saved_answers_forgotten_total",
        "dwhnavigator_feedback_apply_failures_total",
    } <= capture.metric_names()
    finished = {
        labels["status"]: value
        for labels, value in capture.points("dwhnavigator_term_lists_finished_total")
    }
    assert finished == {"completed": 1, "cancelled": 1, "interrupted": 1, "other": 1}
    outcomes = {
        labels["outcome"] for labels, _ in capture.points("dwhnavigator_term_list_terms_total")
    }
    assert outcomes == {"analyst", "reused", "unavailable", "error", "other"}
    reasons = {
        labels["reason"]
        for labels, _ in capture.points("dwhnavigator_term_list_uploads_rejected_total")
    }
    assert reasons == {"term_list_running", "upload_too_large", "other"}
    assert capture.value("dwhnavigator_term_lists_running") == 0
    kinds = {labels["kind"] for labels, _ in capture.points("dwhnavigator_term_list_reports_total")}
    assert kinds == {"list", "item", "other"}
    votes = {
        (labels["scope"], labels["vote"])
        for labels, _ in capture.points("dwhnavigator_feedback_votes_total")
    }
    assert votes == {("table", "up"), ("answer", "down"), ("other", "other")}
    assert capture.value("dwhnavigator_feedback_saved_answers_forgotten_total") == 2
    assert capture.value("dwhnavigator_feedback_apply_failures_total") == 1
