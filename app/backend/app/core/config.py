"""Typed application settings; this is the only application environment boundary."""

import os
import re
from functools import cached_property, lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Annotated, Literal
from urllib.parse import urlsplit

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secret_cipher import decode_encryption_key

_RSA_MINIMUM_KEY_BITS = 2048

RuntimeEnvironment = Literal["local", "nonprod"]
# specs/application-foundation/DOMAIN.md: only this value is the developer machine; every other,
# unknown or unreadable value behaves as nonprod, the closed side.
_LOCAL_ENVIRONMENT_VALUE = "development"
_SERVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")

JwtSigningKey = ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey
JwtVerificationKey = ec.EllipticCurvePublicKey | rsa.RSAPublicKey

# LangChain's langsmith and langgraph-sdk clients reach the paid hosted LangSmith and LangGraph
# services only through these process variables; technology-profile.yml#llm_orchestration forbids
# those services, so a configured key, endpoint or tracing switch stops startup.
_HOSTED_LLM_SERVICE_VARIABLES = (
    "LANGSMITH_API_KEY",
    "LANGSMITH_ENDPOINT",
    "LANGSMITH_RUNS_ENDPOINTS",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_ENDPOINT",
    "LANGGRAPH_API_KEY",
)
_HOSTED_LLM_TRACING_VARIABLES = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
)


class MigrationSettings(BaseSettings):
    """Least-privilege configuration for the schema migration process."""

    model_config = SettingsConfigDict(
        env_prefix="DWHNAVIGATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Validation errors would otherwise echo raw inputs such as the signing key or database
        # credentials into startup logs.
        hide_input_in_errors=True,
    )

    # Required, like in Settings: the connection carries credentials, so no default exists.
    database_url: str

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use the postgresql+asyncpg driver")
        return value


class Settings(BaseSettings):
    """Configuration loaded from prefixed environment variables and an optional .env."""

    model_config = SettingsConfigDict(
        env_prefix="DWHNAVIGATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Validation errors would otherwise echo raw inputs such as the signing key or database
        # credentials into startup logs.
        hide_input_in_errors=True,
    )

    # Mapped by runtime_environment: "development" is local, every other value nonprod.
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    project_name: str = "dwhnavigator"

    api_prefix: str = "/api/dwhnavigator/v1"
    tenant_header: str = "x-tenant-id"
    cors_allow_origins: str = "http://localhost:3000,http://localhost:8080"
    # The exact browser origin of the application (application-foundation 001 Requirement 13): a
    # state-changing request whose Origin header names anything else is refused, and the cookie
    # endpoints require this Origin.
    public_origin: str = "http://localhost:8080"
    # Comma-separated addresses or networks of the ingress controller. X-Forwarded-For is honoured
    # only on a request whose peer is inside one of them; otherwise the header is ignored.
    trusted_proxy_cidrs: str = ""

    # Required in every process because the connection carries credentials. Local Compose builds it
    # from the disposable password of scripts/dev-secrets.sh; with the in-chart database the
    # deployment supplies the DML-only runtime connection through the <release>-database Secret.
    database_url: str

    # Required in every process. rules/58 fixes the asymmetric RS256/ES256 profile: the PEM private
    # key signs, its derived public key verifies. Local Compose receives a disposable development
    # key from scripts/dev-secrets.sh; a missing key in the deployment Secret stops startup instead
    # of enabling a known signing key.
    jwt_private_key: SecretStr
    jwt_algorithm: Literal["ES256", "RS256"] = "ES256"
    jwt_issuer: str = "dwhnavigator"
    jwt_audience: str = "dwhnavigator-api"
    # application-foundation 001 Decision 11: a 15-minute access token, a refresh session idle for
    # at most 60 minutes and never longer than 8 hours after login.
    access_token_expire_minutes: int = 15
    refresh_session_idle_minutes: Annotated[int, Field(ge=1, le=1440)] = 60
    refresh_session_absolute_hours: Annotated[int, Field(ge=1, le=24)] = 8
    # Lifetime of the one-time password the super admin receives when opening or resetting an
    # account (application-foundation 001 Decision 8).
    one_time_password_ttl_hours: Annotated[int, Field(ge=1, le=168)] = 72

    # Encrypts settings the application stores in PostgreSQL (data-dictionary/PRDs/003-llm-connection
    # Requirement 1): standard base64 of 32 random bytes. Empty means nothing can be encrypted.
    settings_encryption_key: SecretStr | None = None

    # OpenTelemetry traces and metrics over OTLP/gRPC (app/core/telemetry.py). Empty disables
    # export; the local observability Compose overlay points it at its collector. Only these typed
    # settings configure telemetry: a process variable starting with OTEL_ stops startup.
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "dwhnavigator-backend"
    otel_traces_sample_ratio: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    otel_metric_export_interval_seconds: Annotated[int, Field(ge=5, le=300)] = 60

    # The local super admin (application-foundation 001 Requirement 17 and 18). When the process
    # receives the start-up password (in nonprod through the runtime Secret) the backend start
    # creates this account once and never changes an existing one. The operator command
    # python -m app.scripts.create_super_admin reads its own password only from its prompt or
    # standard input.
    bootstrap_super_admin_email: str = "admin@example.invalid"
    bootstrap_super_admin_username: str = "super-admin"
    bootstrap_super_admin_password: SecretStr | None = None

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("/"):
            raise ValueError("api_prefix must begin with '/'")
        return normalized

    @field_validator("tenant_header")
    @classmethod
    def validate_tenant_header(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or "_" in normalized:
            raise ValueError("tenant_header must be a non-empty HTTP header name using hyphens")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use the postgresql+asyncpg driver")
        return value

    @field_validator("access_token_expire_minutes")
    @classmethod
    def validate_access_token_expiry(cls, value: int) -> int:
        if not 1 <= value <= 1440:
            raise ValueError("access_token_expire_minutes must be between 1 and 1440")
        return value

    @field_validator("public_origin")
    @classmethod
    def validate_public_origin(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.path
            or parts.query
            or parts.fragment
        ):
            raise ValueError("public_origin must be an exact scheme://host[:port] origin")
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: str) -> str:
        try:
            _parse_networks(value)
        except ValueError:
            raise ValueError("trusted_proxy_cidrs must list IP addresses or networks") from None
        return value

    @field_validator("bootstrap_super_admin_password", "settings_encryption_key", mode="before")
    @classmethod
    def empty_optional_secret_is_absent(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("settings_encryption_key")
    @classmethod
    def validate_settings_encryption_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            try:
                decode_encryption_key(value.get_secret_value())
            except ValueError:
                raise ValueError("settings_encryption_key must be base64 of 32 bytes") from None
        return value

    @field_validator("otel_exporter_otlp_endpoint")
    @classmethod
    def validate_otel_exporter_otlp_endpoint(cls, value: str) -> str:
        endpoint = value.strip()
        if not endpoint:
            return endpoint
        parts = urlsplit(endpoint)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
        ):
            raise ValueError(
                "otel_exporter_otlp_endpoint must be an http(s)://host[:port] collector address"
            )
        return endpoint

    @field_validator("otel_service_name")
    @classmethod
    def validate_otel_service_name(cls, value: str) -> str:
        if _SERVICE_NAME_RE.fullmatch(value) is None:
            raise ValueError("otel_service_name must be a lowercase name of letters, digits and -")
        return value

    @property
    def runtime_environment(self) -> RuntimeEnvironment:
        if self.environment.strip().lower() == _LOCAL_ENVIRONMENT_VALUE:
            return "local"
        return "nonprod"

    @property
    def trusted_proxy_networks(self) -> tuple[IPv4Network | IPv6Network, ...]:
        return _parse_networks(self.trusted_proxy_cidrs)

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @cached_property
    def jwt_signing_key(self) -> JwtSigningKey:
        return _load_signing_key(self.jwt_private_key)

    @cached_property
    def jwt_verification_key(self) -> JwtVerificationKey:
        return self.jwt_signing_key.public_key()

    @model_validator(mode="after")
    def require_key_matching_the_algorithm(self) -> "Settings":
        key = self.jwt_signing_key
        if self.jwt_algorithm == "ES256":
            if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
                raise ValueError("jwt_algorithm ES256 requires a P-256 elliptic-curve private key")
        elif not isinstance(key, rsa.RSAPrivateKey) or key.key_size < _RSA_MINIMUM_KEY_BITS:
            raise ValueError(
                f"jwt_algorithm RS256 requires an RSA private key of at least "
                f"{_RSA_MINIMUM_KEY_BITS} bits"
            )
        return self

    @model_validator(mode="after")
    def reject_hosted_llm_services(self) -> "Settings":
        configured = [name for name in _HOSTED_LLM_SERVICE_VARIABLES if os.environ.get(name)]
        configured += [
            name
            for name in _HOSTED_LLM_TRACING_VARIABLES
            if os.environ.get(name, "").strip().lower() not in {"", "0", "false"}
        ]
        if configured:
            raise ValueError(
                "hosted LangSmith and LangGraph services are not allowed: "
                + ", ".join(sorted(configured))
            )
        return self

    @model_validator(mode="after")
    def reject_untyped_telemetry_configuration(self) -> "Settings":
        # The OpenTelemetry SDK would otherwise read exporter headers, endpoints, certificates and
        # resource attributes from OTEL_* process variables behind the typed settings.
        configured = sorted(name for name in os.environ if name.upper().startswith("OTEL_"))
        if configured:
            raise ValueError(
                "telemetry is configured only through DWHNAVIGATOR_OTEL_* settings: "
                + ", ".join(configured)
            )
        return self

    @model_validator(mode="after")
    def require_https_telemetry_outside_local(self) -> "Settings":
        endpoint = self.otel_exporter_otlp_endpoint
        if (
            endpoint
            and self.runtime_environment == "nonprod"
            and urlsplit(endpoint).scheme != "https"
        ):
            raise ValueError("otel_exporter_otlp_endpoint must use https outside development")
        return self


def _parse_networks(value: str) -> tuple[IPv4Network | IPv6Network, ...]:
    return tuple(
        ip_network(item.strip(), strict=False) for item in value.split(",") if item.strip()
    )


def _load_signing_key(value: SecretStr) -> JwtSigningKey:
    try:
        key = load_pem_private_key(value.get_secret_value().encode("utf-8"), password=None)
    except (TypeError, ValueError, UnsupportedAlgorithm):
        raise ValueError("jwt_private_key must be an unencrypted PEM private key") from None
    if isinstance(key, (ec.EllipticCurvePrivateKey, rsa.RSAPrivateKey)):
        return key
    raise ValueError("jwt_private_key must be an elliptic-curve or RSA private key")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings view."""

    # BaseSettings resolves the required secret from its configured environment source at runtime;
    # static type checkers cannot model that source injection.
    return Settings()  # type: ignore[call-arg]


@lru_cache
def get_migration_settings() -> MigrationSettings:
    """Return the DB-only settings view used by Alembic jobs."""

    # As in get_settings, the required database URL comes from the environment source at runtime.
    return MigrationSettings()  # type: ignore[call-arg]
