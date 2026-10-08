"""OpenTelemetry traces and metrics of the backend process.

application-foundation/PRDs/001-user-accounts Requirement 19 installs this shared path; the
signals, their names and their labels are owned by the "Gözlemlenebilirlik" sections of the PRDs
(specs/application-foundation/DOMAIN.md). Every label value is reduced to a fixed set and anything
else becomes ``other``. Callers pass only classes, counts and durations: no username, password,
token, address, URL, question or dictionary text reaches a span, attribute or metric. Exceptions
are never recorded on spans, because their text can carry an address or a driver message.

Export is configured only through the typed ``DWHNAVIGATOR_OTEL_*`` settings. With an empty
endpoint the no-op providers stay installed, so every helper here is safe to call unconditionally.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from app.core.config import Settings

SCOPE = "dwhnavigator"
SERVICE_VERSION = "0.1.0"
OTHER = "other"

# Fixed label sets of application-foundation/PRDs/001-user-accounts; a value outside its set is
# exported as "other" and never verbatim.
LOGIN_OUTCOMES = frozenset(
    {
        "succeeded",
        "invalid_credentials",
        "user_inactive",
        "one_time_password_expired",
        "password_change_required",
        "rate_limited",
    }
)
PASSWORD_CHANGE_OUTCOMES = frozenset(
    {
        "succeeded",
        "invalid_credentials",
        "user_inactive",
        "one_time_password_expired",
        "password_policy",
        "rate_limited",
    }
)
HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})

# An unreachable collector delays the flush at shutdown by at most this long per signal.
_EXPORT_TIMEOUT_SECONDS = 5


def bounded(value: object, allowed: frozenset[str]) -> str:
    """The value itself when it belongs to ``allowed``; otherwise ``other``."""

    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) and raw in allowed else OTHER


class _Instruments:
    """Every metric of the PRDs, created from one meter."""

    def __init__(self, meter: metrics.Meter) -> None:
        # application-foundation/PRDs/001-user-accounts
        self.auth_login_attempts = meter.create_counter(
            "dwhnavigator_auth_login_attempts_total",
            unit="{attempt}",
            description="Login attempts by outcome class",
        )
        self.auth_password_change_attempts = meter.create_counter(
            "dwhnavigator_auth_password_change_attempts_total",
            unit="{attempt}",
            description="Password change attempts by outcome class",
        )


@dataclass(frozen=True, slots=True)
class _Signals:
    tracer: trace.Tracer
    instruments: _Instruments


def _signals_from(
    tracer_provider: trace.TracerProvider, meter_provider: metrics.MeterProvider
) -> _Signals:
    return _Signals(
        tracer=tracer_provider.get_tracer(SCOPE, SERVICE_VERSION),
        instruments=_Instruments(meter_provider.get_meter(SCOPE, SERVICE_VERSION)),
    )


_NOOP = _signals_from(trace.NoOpTracerProvider(), metrics.NoOpMeterProvider())
_signals = _NOOP


def install(tracer_provider: trace.TracerProvider, meter_provider: metrics.MeterProvider) -> None:
    """Send every later signal of this process to these providers."""

    global _signals
    _signals = _signals_from(tracer_provider, meter_provider)


def uninstall() -> None:
    """Return to the no-op providers."""

    global _signals
    _signals = _NOOP


class TelemetryExport:
    """The OTLP providers of this process; ``shutdown`` flushes and stops them."""

    def __init__(self, tracer_provider: TracerProvider, meter_provider: MeterProvider) -> None:
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider

    def shutdown(self) -> None:
        uninstall()
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()


def configure_telemetry(settings: Settings) -> TelemetryExport | None:
    """Install OTLP/gRPC export when an endpoint is configured; otherwise change nothing."""

    endpoint = settings.otel_exporter_otlp_endpoint.strip()
    if not endpoint:
        return None
    # Imported only when export is on: the exporters load gRPC.
    from opentelemetry.exporter.otlp.proto.grpc import metric_exporter, trace_exporter

    insecure = urlsplit(endpoint).scheme == "http"
    # Built directly, not with Resource.create, so no process variable adds attributes.
    resource = Resource(
        {
            "service.name": settings.otel_service_name,
            "service.version": SERVICE_VERSION,
            "deployment.environment.name": settings.runtime_environment,
        }
    )
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.otel_traces_sample_ratio)),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            trace_exporter.OTLPSpanExporter(
                endpoint=endpoint, insecure=insecure, timeout=_EXPORT_TIMEOUT_SECONDS
            )
        )
    )
    reader = PeriodicExportingMetricReader(
        metric_exporter.OTLPMetricExporter(
            endpoint=endpoint, insecure=insecure, timeout=_EXPORT_TIMEOUT_SECONDS
        ),
        export_interval_millis=settings.otel_metric_export_interval_seconds * 1000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    install(tracer_provider, meter_provider)
    return TelemetryExport(tracer_provider, meter_provider)


def _content_free_span(name: str, kind: SpanKind, attributes: dict[str, Any]) -> Any:
    return _signals.tracer.start_as_current_span(
        name,
        kind=kind,
        attributes=attributes,
        record_exception=False,
        set_status_on_exception=False,
    )


# --- HTTP server requests ----------------------------------------------------------------------


class HttpServerSpan:
    """The server span of one request; ``complete`` names it after the matched route template."""

    def __init__(self, span: Span, method: str) -> None:
        self._span = span
        self._method = method

    def complete(self, route_template: str, status_code: int) -> None:
        self._span.update_name(f"{self._method} {route_template}")
        self._span.set_attribute("http.route", route_template)
        self._span.set_attribute("http.response.status_code", status_code)
        if status_code >= 500:
            # A status without description: the exception text never reaches the trace.
            self._span.set_status(Status(StatusCode.ERROR))


@contextmanager
def http_server_span(method: str) -> Iterator[HttpServerSpan]:
    """Method, route template and status only; never the raw path, query, headers or body."""

    bounded_method = method if method in HTTP_METHODS else "_OTHER"
    with _content_free_span(
        bounded_method, SpanKind.SERVER, {"http.request.method": bounded_method}
    ) as span:
        yield HttpServerSpan(span, bounded_method)


# --- Login and password change (application-foundation/PRDs/001-user-accounts) ------------------


def record_login_attempt(outcome: str) -> None:
    _signals.instruments.auth_login_attempts.add(1, {"outcome": bounded(outcome, LOGIN_OUTCOMES)})


def record_password_change_attempt(outcome: str) -> None:
    _signals.instruments.auth_password_change_attempts.add(
        1, {"outcome": bounded(outcome, PASSWORD_CHANGE_OUTCOMES)}
    )
