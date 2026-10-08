"""Typed settings of application-foundation/PRDs/001-user-accounts and the settings encryption key.

Requirement 9 (trusted proxy networks), 13 (application origin), 17 (super admin), 19 (telemetry),
Decision 8 and 11 (lifetimes), the "Ortam" term of the domain document and
data-dictionary/PRDs/003-llm-connection Requirement 1 (encryption key).
"""

import base64
import os
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

pytestmark = pytest.mark.unit

_KEPT_VARIABLES = {"DWHNAVIGATOR_JWT_PRIVATE_KEY", "DWHNAVIGATOR_DATABASE_URL"}


@pytest.fixture(autouse=True)
def _defaults_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert the typed defaults, not the values the local Compose stack injects."""

    for name in list(os.environ):
        if name.startswith("DWHNAVIGATOR_") and name not in _KEPT_VARIABLES:
            monkeypatch.delenv(name)


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("development", "local"),
        ("DEVELOPMENT", "local"),
        (" development ", "local"),
        ("staging", "nonprod"),
        ("production", "nonprod"),
        ("test", "nonprod"),
        ("", "nonprod"),
        ("unknown-value", "nonprod"),
    ),
)
def test_environment_maps_to_local_or_fails_towards_nonprod(value: str, expected: str) -> None:
    assert _settings(environment=value).runtime_environment == expected


def test_session_and_one_time_password_lifetimes_follow_the_accepted_decisions() -> None:
    settings = _settings()
    assert settings.access_token_expire_minutes == 15
    assert settings.refresh_session_idle_minutes == 60
    assert settings.refresh_session_absolute_hours == 8
    assert settings.one_time_password_ttl_hours == 72


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("one_time_password_ttl_hours", 0),
        ("one_time_password_ttl_hours", 169),
        ("refresh_session_idle_minutes", 0),
        ("refresh_session_absolute_hours", 25),
        ("access_token_expire_minutes", 0),
    ),
)
def test_lifetimes_outside_their_range_stop_start_up(field: str, value: int) -> None:
    with pytest.raises(ValidationError, match=field):
        _settings(**{field: value})


def test_one_time_password_lifetime_accepts_its_bounds() -> None:
    assert _settings(one_time_password_ttl_hours=1).one_time_password_ttl_hours == 1
    assert _settings(one_time_password_ttl_hours=168).one_time_password_ttl_hours == 168


def test_empty_optional_secrets_mean_not_configured() -> None:
    settings = _settings(bootstrap_super_admin_password="", settings_encryption_key="")
    assert settings.bootstrap_super_admin_password is None
    assert settings.settings_encryption_key is None


def test_optional_secrets_are_not_rendered() -> None:
    key = base64.b64encode(os.urandom(32)).decode()
    settings = _settings(
        bootstrap_super_admin_password="distinct-marker-secret", settings_encryption_key=key
    )
    rendered = repr(settings) + str(settings.model_dump())
    assert "distinct-marker-secret" not in rendered
    assert key not in rendered


def test_the_settings_encryption_key_is_optional_and_must_be_32_bytes() -> None:
    key = base64.b64encode(os.urandom(32)).decode()
    assert _settings().settings_encryption_key is None
    assert _settings(settings_encryption_key=key).settings_encryption_key is not None
    for invalid in ("kisa-anahtar", base64.b64encode(os.urandom(16)).decode()):
        with pytest.raises(ValidationError, match="settings_encryption_key") as raised:
            _settings(settings_encryption_key=invalid)
        assert invalid not in str(raised.value)


def test_trusted_proxy_networks_are_parsed_and_validated() -> None:
    assert _settings().trusted_proxy_networks == ()
    settings = _settings(trusted_proxy_cidrs="10.42.0.0/16, 192.168.1.10")
    assert [str(network) for network in settings.trusted_proxy_networks] == [
        "10.42.0.0/16",
        "192.168.1.10/32",
    ]
    with pytest.raises(ValidationError, match="trusted_proxy_cidrs"):
        _settings(trusted_proxy_cidrs="not-a-network")


def test_public_origin_must_be_an_exact_origin() -> None:
    assert _settings().public_origin == "http://localhost:8080"
    assert _settings(public_origin="https://app.example.test").public_origin == (
        "https://app.example.test"
    )
    for value in ("https://app.example.test/", "https://app.example.test/path", "app.example"):
        with pytest.raises(ValidationError, match="public_origin"):
            _settings(public_origin=value)


def test_telemetry_is_off_by_default_and_bounded() -> None:
    settings = _settings()
    assert settings.otel_exporter_otlp_endpoint == ""
    assert settings.otel_service_name == "dwhnavigator-backend"
    assert settings.otel_traces_sample_ratio == 1.0
    assert settings.otel_metric_export_interval_seconds == 60
    for field, value in (
        ("otel_traces_sample_ratio", 1.5),
        ("otel_traces_sample_ratio", -0.1),
        ("otel_metric_export_interval_seconds", 4),
        ("otel_metric_export_interval_seconds", 301),
    ):
        with pytest.raises(ValidationError):
            _settings(**{field: value})


@pytest.mark.parametrize(
    "endpoint",
    (
        "otel-collector:4317",
        "grpc://otel-collector:4317",
        "http://user:secret@otel-collector:4317",
        "http://otel-collector:4317/v1/traces",
        "http://otel-collector:4317?token=x",
        "https://",
    ),
)
def test_collector_endpoint_must_be_a_bare_address(endpoint: str) -> None:
    with pytest.raises(ValidationError) as raised:
        _settings(environment="development", otel_exporter_otlp_endpoint=endpoint)
    assert "secret" not in str(raised.value)


def test_collector_endpoint_accepts_an_address_and_trims_it() -> None:
    settings = _settings(
        environment="development", otel_exporter_otlp_endpoint=" http://otel-collector:4317 "
    )
    assert settings.otel_exporter_otlp_endpoint == "http://otel-collector:4317"


def test_outside_development_the_collector_endpoint_must_be_https() -> None:
    with pytest.raises(ValidationError, match="https"):
        _settings(environment="staging", otel_exporter_otlp_endpoint="http://collector:4317")
    settings = _settings(environment="staging", otel_exporter_otlp_endpoint="https://c:4317")
    assert settings.otel_exporter_otlp_endpoint == "https://c:4317"


@pytest.mark.parametrize("name", ("Backend", "dwh navigator", "-backend", ""))
def test_service_name_is_a_plain_lowercase_name(name: str) -> None:
    with pytest.raises(ValidationError):
        _settings(otel_service_name=name)


@pytest.mark.parametrize(
    "variable", ("OTEL_EXPORTER_OTLP_HEADERS", "OTEL_RESOURCE_ATTRIBUTES", "otel_sdk_disabled")
)
def test_otel_process_variables_stop_start_up(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "authorization=Bearer do-not-echo")
    with pytest.raises(ValidationError) as raised:
        _settings()
    assert variable in str(raised.value)
    assert "do-not-echo" not in str(raised.value)


def test_super_admin_defaults_open_no_account() -> None:
    settings = _settings()
    assert settings.bootstrap_super_admin_password is None
    assert settings.bootstrap_super_admin_username == "super-admin"
