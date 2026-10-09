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
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit

from opentelemetry import context as otel_context
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
# Fixed label sets of data-dictionary/PRDs/003-llm-connection (Gözlemlenebilirlik).
LLM_PURPOSES = frozenset({"analysis", "connection_test", "evaluation"})
LLM_OUTCOMES = frozenset(
    {
        "ok",
        "not_configured",
        "key_unreadable",
        "network_policy_denied",
        "name_unresolved",
        "connect_refused",
        "connect_error",
        "tls_error",
        "timeout",
        "unauthorized",
        "context_exceeded",
        "upstream_status",
        "invalid_response",
        "invalid_json",
        "response_too_large",
        "cancelled",
    }
)
LLM_PROBE_OPERATIONS = frozenset({"health", "models", "inventory"})
LLM_TOKEN_KINDS = frozenset({"prompt", "completion"})
LLM_FEATURES = frozenset(
    {"system_role", "response_format", "reasoning_effort", "seed", "chat_template_kwargs"}
)
# Fixed label sets of data-dictionary/PRDs/001-dictionary-management (Gözlemlenebilirlik).
DICTIONARY_IMPORT_OUTCOMES = frozenset(
    {"created", "unchanged", "invalid", "too_large", "unsupported_type", "conflict", "error"}
)
DICTIONARY_CHANNELS = frozenset({"arayuz", "betik"})
DICTIONARY_EXPORT_KINDS = frozenset({"dictionary", "template"})
# Fixed label sets of data-dictionary/PRDs/009-search-settings (Gözlemlenebilirlik).
SEARCH_TRIGGERS = frozenset({"startup", "dictionary", "terms", "stopwords", "settings", "manual"})
SEARCH_BUILD_OUTCOMES = frozenset({"ok", "failed"})
SEARCH_CHANGE_OUTCOMES = frozenset({"applied", "unchanged", "failed", "busy"})

# Fixed label sets of data-dictionary/PRDs/004-question-analysis and 008-analysis-records.
ANALYSIS_ORIGINS = frozenset({"question", "list"})
ANALYSIS_OUTCOMES = frozenset(
    {"analyst", "reused", "unavailable", "failed", "cancelled", "interrupted"}
)
ANALYSIS_VERDICTS = frozenset({"var", "kismen_var", "bulunamadi"})
ANALYSIS_STEPS = frozenset(
    {
        "saved_answer_lookup",
        "queue",
        "model_check",
        "rule_hints",
        "shortlist",
        "family_search",
        "analyst_report",
    }
)
SAVED_ANSWER_LOOKUP_RESULTS = frozenset(
    {"same_question", "same_meaning", "miss", "disabled", "error"}
)
SAVED_ANSWER_WRITE_RESULTS = frozenset({"stored", "skipped", "error"})
REPORT_RESULTS = frozenset({"ok", "error"})

# Fixed label sets of data-dictionary/PRDs/005-list-search.
TERM_LIST_STATUSES = frozenset({"completed", "cancelled", "interrupted"})
TERM_LIST_TERM_OUTCOMES = frozenset({"analyst", "reused", "unavailable", "error"})
TERM_LIST_REJECT_REASONS = frozenset(
    {
        "upload_too_large",
        "unsupported_media_type",
        "term_list_not_xlsx",
        "term_list_too_large_unpacked",
        "term_list_too_many_rows",
        "term_list_layout_invalid",
        "term_list_term_too_long",
        "term_list_too_many_terms",
        "term_list_running",
    }
)
TERM_LIST_REPORT_KINDS = frozenset({"list", "item"})

# Fixed label sets of data-dictionary/PRDs/006-answer-feedback.
FEEDBACK_SCOPES = frozenset({"table", "answer"})
FEEDBACK_VOTES = frozenset({"up", "down"})

# Fixed label sets of data-dictionary/PRDs/007-dictionary-explorer.
EXPLORER_ENDPOINTS = frozenset({"galaxy", "search", "table"})
EXPLORER_OUTCOMES = frozenset({"ok", "not_found", "not_ready", "invalid", "error"})
EXPLORER_SEARCH_MODES = frozenset({"browse", "name_only", "full"})

# An analysis waits in the queue and runs for up to an hour of model time.
_ANALYSIS_BUCKETS = (0.5, 1, 2, 5, 10, 20, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1800, 3600)

# A chat call reads for up to timeout_seconds (at most 3600 s) after waiting for a slot.
_LLM_BUCKETS = (0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300, 600, 900, 1800, 2700, 3600)

# A table search answers in milliseconds; the content layer can take a second on a large dictionary.
_EXPLORER_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)

# Reading, checking and writing a dictionary of up to 200,000 rows; building the search index.
_IMPORT_BUCKETS = (0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 45, 60, 90, 120)

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
        # data-dictionary/PRDs/003-llm-connection
        self.llm_calls = meter.create_counter(
            "dwhnavigator_llm_calls_total",
            unit="{call}",
            description="Chat calls to the model server by purpose and outcome class",
        )
        self.llm_call_duration = meter.create_histogram(
            "dwhnavigator_llm_call_duration_seconds",
            unit="s",
            description="Duration of chat calls, slot wait included, by purpose and outcome class",
            explicit_bucket_boundaries_advisory=_LLM_BUCKETS,
        )
        self.llm_inflight_calls = meter.create_up_down_counter(
            "dwhnavigator_llm_inflight_calls",
            unit="{call}",
            description="Chat requests holding a slot",
        )
        self.llm_waiting_calls = meter.create_up_down_counter(
            "dwhnavigator_llm_waiting_calls",
            unit="{call}",
            description="Chat calls waiting for a slot",
        )
        self.llm_tokens = meter.create_counter(
            "dwhnavigator_llm_tokens_total",
            unit="{token}",
            description="Prompt and completion tokens the model server reported",
        )
        self.llm_adaptations = meter.create_counter(
            "dwhnavigator_llm_adaptations_total",
            unit="{adaptation}",
            description="Request features dropped after the server refused them",
        )
        self.llm_probes = meter.create_counter(
            "dwhnavigator_llm_probes_total",
            unit="{probe}",
            description="Model server /models reads by operation and outcome class",
        )
        # data-dictionary/PRDs/001-dictionary-management
        self.dictionary_imports = meter.create_counter(
            "dwhnavigator_dictionary_imports_total",
            unit="{import}",
            description="Dictionary imports by outcome class and channel",
        )
        self.dictionary_import_duration = meter.create_histogram(
            "dwhnavigator_dictionary_import_duration_seconds",
            unit="s",
            description="Reading, checking and writing one dictionary import, by outcome class",
            explicit_bucket_boundaries_advisory=_IMPORT_BUCKETS,
        )
        self.dictionary_exports = meter.create_counter(
            "dwhnavigator_dictionary_exports_total",
            unit="{export}",
            description="Dictionary and empty template downloads",
        )
        self.dictionary_active_columns = meter.create_gauge(
            "dwhnavigator_dictionary_active_columns",
            unit="{column}",
            description="Valid columns of the active dictionary version in the serving index",
        )
        self.dictionary_active_tables = meter.create_gauge(
            "dwhnavigator_dictionary_active_tables",
            unit="{table}",
            description="Tables of the active dictionary version in the serving index",
        )
        # data-dictionary/PRDs/009-search-settings
        self.search_index_builds = meter.create_counter(
            "dwhnavigator_search_index_builds_total",
            unit="{build}",
            description="Search index builds by trigger and outcome",
        )
        self.search_index_build_duration = meter.create_histogram(
            "dwhnavigator_search_index_build_duration_seconds",
            unit="s",
            description="Duration of search index builds by trigger",
            explicit_bucket_boundaries_advisory=_IMPORT_BUCKETS,
        )
        self.search_index_ready = meter.create_gauge(
            "dwhnavigator_search_index_ready",
            unit="1",
            description="1 when an index serves and matches the database, otherwise 0",
        )
        self.search_changes = meter.create_counter(
            "dwhnavigator_search_changes_total",
            unit="{change}",
            description="Changes of the search data through the change queue by outcome",
        )

        # data-dictionary/PRDs/004-question-analysis
        self.analyses_started = meter.create_counter(
            "dwhnavigator_analyses_started_total",
            unit="{analysis}",
            description="Analysis jobs that started running, by origin",
        )
        self.analyses_finished = meter.create_counter(
            "dwhnavigator_analyses_finished_total",
            unit="{analysis}",
            description="Analysis jobs that reached their end, by origin and outcome",
        )
        self.analysis_duration = meter.create_histogram(
            "dwhnavigator_analysis_duration_seconds",
            unit="s",
            description="From acceptance to the end of an analysis job, by origin and outcome",
            explicit_bucket_boundaries_advisory=_ANALYSIS_BUCKETS,
        )
        self.analysis_queue_wait = meter.create_histogram(
            "dwhnavigator_analysis_queue_wait_seconds",
            unit="s",
            description="Time an analysis job waited in the queue, by origin",
            explicit_bucket_boundaries_advisory=_ANALYSIS_BUCKETS,
        )
        self.analysis_step_duration = meter.create_histogram(
            "dwhnavigator_analysis_step_duration_seconds",
            unit="s",
            description="Duration of the main steps of analysis jobs, by step key",
            explicit_bucket_boundaries_advisory=_ANALYSIS_BUCKETS,
        )
        self.analysis_queue_length = meter.create_up_down_counter(
            "dwhnavigator_analysis_queue_length",
            unit="{analysis}",
            description="Analysis jobs waiting in the queue",
        )
        self.analyses_running = meter.create_up_down_counter(
            "dwhnavigator_analyses_running",
            unit="{analysis}",
            description="Analysis jobs running",
        )
        self.analysis_verdicts = meter.create_counter(
            "dwhnavigator_analysis_verdicts_total",
            unit="{analysis}",
            description="Answers of completed analysis jobs by verdict",
        )
        self.analysis_validation_dropped = meter.create_counter(
            "dwhnavigator_analysis_validation_dropped_total",
            unit="{name}",
            description="Names and sentences the dictionary check dropped from model answers",
        )
        self.saved_answer_lookups = meter.create_counter(
            "dwhnavigator_saved_answer_lookups_total",
            unit="{lookup}",
            description="Saved answer lookups by result",
        )
        self.saved_answer_writes = meter.create_counter(
            "dwhnavigator_saved_answer_writes_total",
            unit="{write}",
            description="Saved answer writes by result",
        )
        self.analysis_streams_open = meter.create_up_down_counter(
            "dwhnavigator_analysis_streams_open",
            unit="{stream}",
            description="Open live progress streams of analysis jobs",
        )
        self.analysis_reports = meter.create_counter(
            "dwhnavigator_analysis_reports_total",
            unit="{report}",
            description="Single-question Excel reports by result",
        )
        # data-dictionary/PRDs/008-analysis-records
        self.analysis_records_deleted = meter.create_counter(
            "dwhnavigator_analysis_records_deleted_total",
            unit="{record}",
            description="Analysis records a manager deleted",
        )
        # data-dictionary/PRDs/005-list-search
        self.term_lists_started = meter.create_counter(
            "dwhnavigator_term_lists_started_total",
            unit="{list}",
            description="Term lists started",
        )
        self.term_lists_finished = meter.create_counter(
            "dwhnavigator_term_lists_finished_total",
            unit="{list}",
            description="Term lists that stopped running, by status",
        )
        self.term_list_terms = meter.create_counter(
            "dwhnavigator_term_list_terms_total",
            unit="{term}",
            description="Terms of term lists that ended, by outcome (a stopped term is not counted)",
        )
        self.term_list_uploads_rejected = meter.create_counter(
            "dwhnavigator_term_list_uploads_rejected_total",
            unit="{upload}",
            description="Term list uploads refused, by reason",
        )
        self.term_lists_running = meter.create_up_down_counter(
            "dwhnavigator_term_lists_running",
            unit="{list}",
            description="Term lists running in this process (0 or 1)",
        )
        self.term_list_reports = meter.create_counter(
            "dwhnavigator_term_list_reports_total",
            unit="{report}",
            description="Term list and term Excel reports downloaded, by kind",
        )
        # data-dictionary/PRDs/006-answer-feedback
        self.feedback_votes = meter.create_counter(
            "dwhnavigator_feedback_votes_total",
            unit="{vote}",
            description="Votes recorded, by scope and vote",
        )
        self.feedback_saved_answers_forgotten = meter.create_counter(
            "dwhnavigator_feedback_saved_answers_forgotten_total",
            unit="{answer}",
            description="Saved answers deleted because enough people found the answer useless",
        )
        self.feedback_apply_failures = meter.create_counter(
            "dwhnavigator_feedback_apply_failures_total",
            unit="{failure}",
            description="Answers returned without votes because applying the votes failed",
        )
        # data-dictionary/PRDs/007-dictionary-explorer
        self.explorer_requests = meter.create_counter(
            "dwhnavigator_explorer_requests_total",
            unit="{request}",
            description="Dictionary explorer requests, by endpoint and outcome",
        )
        self.explorer_search_duration = meter.create_histogram(
            "dwhnavigator_explorer_search_duration_seconds",
            unit="s",
            description="Duration of table searches, by mode",
            explicit_bucket_boundaries_advisory=_EXPLORER_BUCKETS,
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


# --- Model calls (data-dictionary/PRDs/003-llm-connection) --------------------------------------


@dataclass
class LlmChatRecord:
    """What a chat span reports at its end; classes and counts only."""

    outcome: str = ""
    http_status: int | None = None
    requests: int = 0
    adaptations: int = 0
    repaired: bool = False


@dataclass
class LlmProbeRecord:
    outcome: str = ""
    cached: bool = False


def _fails(outcome: str) -> bool:
    return outcome not in ("ok", "cancelled")


@contextmanager
def llm_chat_span(purpose: str) -> Iterator[LlmChatRecord]:
    """The ``llm chat`` span: purpose, outcome, HTTP status, request, adaptation and repair counts.

    No address, model, prompt, reply or error text reaches it.
    """

    record = LlmChatRecord()
    with _content_free_span(
        "llm chat",
        SpanKind.CLIENT,
        {"dwhnavigator.llm.purpose": bounded(purpose, LLM_PURPOSES)},
    ) as span:
        try:
            yield record
        finally:
            outcome = bounded(record.outcome, LLM_OUTCOMES)
            span.set_attribute("dwhnavigator.llm.outcome", outcome)
            if record.http_status is not None:
                span.set_attribute("http.response.status_code", record.http_status)
            span.set_attribute("dwhnavigator.llm.requests", record.requests)
            span.set_attribute("dwhnavigator.llm.adaptations", record.adaptations)
            span.set_attribute("dwhnavigator.llm.repaired", record.repaired)
            if _fails(outcome):
                span.set_status(Status(StatusCode.ERROR))


@contextmanager
def llm_probe_span(operation: str) -> Iterator[LlmProbeRecord]:
    """The ``llm probe`` span of one ``/models`` read: operation, outcome and cache use."""

    record = LlmProbeRecord()
    with _content_free_span(
        "llm probe",
        SpanKind.CLIENT,
        {"dwhnavigator.llm.operation": bounded(operation, LLM_PROBE_OPERATIONS)},
    ) as span:
        try:
            yield record
        finally:
            outcome = bounded(record.outcome, LLM_OUTCOMES)
            span.set_attribute("dwhnavigator.llm.outcome", outcome)
            span.set_attribute("dwhnavigator.llm.cached", record.cached)
            if _fails(outcome):
                span.set_status(Status(StatusCode.ERROR))


def record_llm_call(
    *,
    purpose: str,
    outcome: str,
    duration_seconds: float,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    labels = {"purpose": bounded(purpose, LLM_PURPOSES), "outcome": bounded(outcome, LLM_OUTCOMES)}
    instruments = _signals.instruments
    instruments.llm_calls.add(1, labels)
    instruments.llm_call_duration.record(duration_seconds, labels)
    if prompt_tokens:
        instruments.llm_tokens.add(prompt_tokens, {"kind": "prompt"})
    if completion_tokens:
        instruments.llm_tokens.add(completion_tokens, {"kind": "completion"})


def llm_waiting_changed(delta: int) -> None:
    _signals.instruments.llm_waiting_calls.add(delta)


def llm_inflight_changed(delta: int) -> None:
    _signals.instruments.llm_inflight_calls.add(delta)


def record_llm_adaptation(feature: str) -> None:
    _signals.instruments.llm_adaptations.add(1, {"feature": bounded(feature, LLM_FEATURES)})


def record_llm_probe(*, operation: str, outcome: str) -> None:
    _signals.instruments.llm_probes.add(
        1,
        {
            "operation": bounded(operation, LLM_PROBE_OPERATIONS),
            "outcome": bounded(outcome, LLM_OUTCOMES),
        },
    )


# --- Dictionary (data-dictionary/PRDs/001-dictionary-management) --------------------------------


@dataclass
class DictionaryImportRecord:
    """What the ``dictionary import`` span reports at its end; classes and counts only."""

    outcome: str = "error"
    row_count: int = 0


@contextmanager
def dictionary_import_span(channel: str) -> Iterator[DictionaryImportRecord]:
    """The ``dictionary import`` span: outcome, channel, row count and duration; no content."""

    record = DictionaryImportRecord()
    bounded_channel = bounded(channel, DICTIONARY_CHANNELS)
    started = perf_counter()
    with _content_free_span(
        "dictionary import",
        SpanKind.INTERNAL,
        {"dwhnavigator.dictionary.channel": bounded_channel},
    ) as span:
        try:
            yield record
        finally:
            seconds = perf_counter() - started
            outcome = bounded(record.outcome, DICTIONARY_IMPORT_OUTCOMES)
            span.set_attribute("dwhnavigator.dictionary.outcome", outcome)
            span.set_attribute("dwhnavigator.dictionary.row_count", record.row_count)
            span.set_attribute("dwhnavigator.duration_ms", round(seconds * 1000))
            if outcome == "error":
                span.set_status(Status(StatusCode.ERROR))
            instruments = _signals.instruments
            instruments.dictionary_imports.add(1, {"outcome": outcome, "channel": bounded_channel})
            instruments.dictionary_import_duration.record(seconds, {"outcome": outcome})


def record_dictionary_export(kind: str) -> None:
    _signals.instruments.dictionary_exports.add(1, {"kind": bounded(kind, DICTIONARY_EXPORT_KINDS)})


def set_active_dictionary(columns: int, tables: int) -> None:
    _signals.instruments.dictionary_active_columns.set(columns)
    _signals.instruments.dictionary_active_tables.set(tables)


# --- Search index (data-dictionary/PRDs/009-search-settings) -----------------------------------


@dataclass
class SearchChangeRecord:
    outcome: str = "failed"


@dataclass
class SearchBuildRecord:
    outcome: str = "failed"
    columns: int = 0
    objects: int = 0


@contextmanager
def search_change_span(trigger: str) -> Iterator[SearchChangeRecord]:
    """The ``search_change.apply`` span of one change and its ``changes_total`` point."""

    record = SearchChangeRecord()
    bounded_trigger = bounded(trigger, SEARCH_TRIGGERS)
    with _content_free_span(
        "search_change.apply",
        SpanKind.INTERNAL,
        {"dwhnavigator.search.trigger": bounded_trigger},
    ) as span:
        try:
            yield record
        finally:
            outcome = bounded(record.outcome, SEARCH_CHANGE_OUTCOMES)
            span.set_attribute("dwhnavigator.search.outcome", outcome)
            if outcome == "failed":
                span.set_status(Status(StatusCode.ERROR))
            _signals.instruments.search_changes.add(
                1, {"trigger": bounded_trigger, "outcome": outcome}
            )


def record_search_change(trigger: str, outcome: str) -> None:
    """A change that never entered the queue (``busy``)."""

    _signals.instruments.search_changes.add(
        1,
        {
            "trigger": bounded(trigger, SEARCH_TRIGGERS),
            "outcome": bounded(outcome, SEARCH_CHANGE_OUTCOMES),
        },
    )


@contextmanager
def search_index_build_span(trigger: str) -> Iterator[SearchBuildRecord]:
    """The ``search_index.build`` span: trigger, outcome, column and table counts."""

    record = SearchBuildRecord()
    bounded_trigger = bounded(trigger, SEARCH_TRIGGERS)
    started = perf_counter()
    with _content_free_span(
        "search_index.build",
        SpanKind.INTERNAL,
        {"dwhnavigator.search.trigger": bounded_trigger},
    ) as span:
        try:
            yield record
        finally:
            outcome = bounded(record.outcome, SEARCH_BUILD_OUTCOMES)
            span.set_attribute("dwhnavigator.search.outcome", outcome)
            span.set_attribute("dwhnavigator.search.columns", record.columns)
            span.set_attribute("dwhnavigator.search.objects", record.objects)
            if outcome == "failed":
                span.set_status(Status(StatusCode.ERROR))
            instruments = _signals.instruments
            instruments.search_index_builds.add(1, {"trigger": bounded_trigger, "outcome": outcome})
            instruments.search_index_build_duration.record(
                perf_counter() - started, {"trigger": bounded_trigger}
            )


def set_search_index_ready(ready: bool) -> None:
    _signals.instruments.search_index_ready.set(1 if ready else 0)


# --- Analysis jobs (data-dictionary/PRDs/004-question-analysis) ----------------------------------


def verdict_label(verdict: str) -> str:
    """``VAR`` → ``var``, ``KISMEN VAR`` → ``kismen_var``, ``BULUNAMADI`` → ``bulunamadi``."""

    return bounded(verdict.lower().replace(" ", "_"), ANALYSIS_VERDICTS)


@dataclass
class AnalysisRunRecord:
    """What the ``analysis.run`` span reports at its end; classes and counts only."""

    outcome: str = "failed"
    verdict: str = ""
    suggestions: int = 0
    dropped: int = 0
    llm_calls: int = 0


@contextmanager
def analysis_run_span(origin: str) -> Iterator[AnalysisRunRecord]:
    """One analysis job's ``analysis.run`` span; its step spans and model calls go below it."""

    record = AnalysisRunRecord()
    with _content_free_span(
        "analysis.run",
        SpanKind.INTERNAL,
        {"dwhnavigator.analysis.origin": bounded(origin, ANALYSIS_ORIGINS)},
    ) as span:
        try:
            yield record
        finally:
            outcome = bounded(record.outcome, ANALYSIS_OUTCOMES)
            span.set_attribute("dwhnavigator.analysis.outcome", outcome)
            if record.verdict:
                span.set_attribute("dwhnavigator.analysis.verdict", verdict_label(record.verdict))
            span.set_attribute("dwhnavigator.analysis.suggestions", record.suggestions)
            span.set_attribute("dwhnavigator.analysis.dropped", record.dropped)
            span.set_attribute("dwhnavigator.analysis.llm_calls", record.llm_calls)
            if outcome == "failed":
                span.set_status(Status(StatusCode.ERROR))


@dataclass
class StepSpan:
    span: Span
    token: object | None


def open_step_span(key: str, *, start_time_ns: int | None = None, current: bool = True) -> StepSpan:
    """A main step of an analysis job, named by its fixed key. ``current`` makes it the parent of
    what runs inside the step in this thread (the model call spans); the step's end must then
    come from the same context."""

    span = _signals.tracer.start_span(
        bounded(key, ANALYSIS_STEPS),
        kind=SpanKind.INTERNAL,
        start_time=start_time_ns,
        record_exception=False,
        set_status_on_exception=False,
    )
    token = otel_context.attach(trace.set_span_in_context(span)) if current else None
    return StepSpan(span, token)


def close_step_span(step: StepSpan, *, error: bool) -> None:
    if step.token is not None:
        otel_context.detach(step.token)  # type: ignore[arg-type]
    if error:
        step.span.set_status(Status(StatusCode.ERROR))
    step.span.end()


def record_analysis_started(origin: str, queue_wait_seconds: float) -> None:
    labels = {"origin": bounded(origin, ANALYSIS_ORIGINS)}
    _signals.instruments.analyses_started.add(1, labels)
    _signals.instruments.analysis_queue_wait.record(queue_wait_seconds, labels)


def record_analysis_finished(
    *, origin: str, outcome: str, duration_seconds: float, verdict: str, dropped: int
) -> None:
    labels = {
        "origin": bounded(origin, ANALYSIS_ORIGINS),
        "outcome": bounded(outcome, ANALYSIS_OUTCOMES),
    }
    instruments = _signals.instruments
    instruments.analyses_finished.add(1, labels)
    instruments.analysis_duration.record(duration_seconds, labels)
    if verdict:
        instruments.analysis_verdicts.add(1, {"verdict": verdict_label(verdict)})
    if dropped:
        instruments.analysis_validation_dropped.add(dropped)


def record_analysis_step(key: str, seconds: float) -> None:
    _signals.instruments.analysis_step_duration.record(
        seconds, {"step": bounded(key, ANALYSIS_STEPS)}
    )


def analysis_queue_changed(delta: int) -> None:
    _signals.instruments.analysis_queue_length.add(delta)


def analyses_running_changed(delta: int) -> None:
    _signals.instruments.analyses_running.add(delta)


def analysis_streams_changed(delta: int) -> None:
    _signals.instruments.analysis_streams_open.add(delta)


def record_saved_answer_lookup(result: str) -> None:
    _signals.instruments.saved_answer_lookups.add(
        1, {"result": bounded(result, SAVED_ANSWER_LOOKUP_RESULTS)}
    )


def record_saved_answer_write(result: str) -> None:
    _signals.instruments.saved_answer_writes.add(
        1, {"result": bounded(result, SAVED_ANSWER_WRITE_RESULTS)}
    )


def record_analysis_report(result: str) -> None:
    _signals.instruments.analysis_reports.add(1, {"result": bounded(result, REPORT_RESULTS)})


# --- Analysis records (data-dictionary/PRDs/008-analysis-records) --------------------------------


def record_analysis_records_deleted(count: int) -> None:
    if count:
        _signals.instruments.analysis_records_deleted.add(count)


# --- Term lists (data-dictionary/PRDs/005-list-search) ------------------------------------------


def record_term_list_started() -> None:
    _signals.instruments.term_lists_started.add(1)


def record_term_list_finished(status: str) -> None:
    _signals.instruments.term_lists_finished.add(1, {"status": bounded(status, TERM_LIST_STATUSES)})


def record_term_list_term(outcome: str) -> None:
    _signals.instruments.term_list_terms.add(
        1, {"outcome": bounded(outcome, TERM_LIST_TERM_OUTCOMES)}
    )


def record_term_list_upload_rejected(reason: str) -> None:
    _signals.instruments.term_list_uploads_rejected.add(
        1, {"reason": bounded(reason, TERM_LIST_REJECT_REASONS)}
    )


def term_lists_running_changed(delta: int) -> None:
    _signals.instruments.term_lists_running.add(delta)


def record_term_list_report(kind: str) -> None:
    _signals.instruments.term_list_reports.add(1, {"kind": bounded(kind, TERM_LIST_REPORT_KINDS)})


# --- Votes (data-dictionary/PRDs/006-answer-feedback) -------------------------------------------


def record_feedback_vote(scope: str, vote: str) -> None:
    _signals.instruments.feedback_votes.add(
        1, {"scope": bounded(scope, FEEDBACK_SCOPES), "vote": bounded(vote, FEEDBACK_VOTES)}
    )


def record_feedback_saved_answers_forgotten(count: int) -> None:
    if count:
        _signals.instruments.feedback_saved_answers_forgotten.add(count)


def record_feedback_apply_failure() -> None:
    _signals.instruments.feedback_apply_failures.add(1)


# --- Dictionary explorer (data-dictionary/PRDs/007-dictionary-explorer) ------------------------


def record_explorer_request(endpoint: str, outcome: str) -> None:
    _signals.instruments.explorer_requests.add(
        1,
        {
            "endpoint": bounded(endpoint, EXPLORER_ENDPOINTS),
            "outcome": bounded(outcome, EXPLORER_OUTCOMES),
        },
    )


@dataclass
class ExplorerSearchRecord:
    """What the ``explorer search`` span reports: the mode and the number of tables only."""

    results: int = 0


@contextmanager
def explorer_search_span(mode: str) -> Iterator[ExplorerSearchRecord]:
    """One table search, without its text; the duration is recorded by mode."""

    record = ExplorerSearchRecord()
    bounded_mode = bounded(mode, EXPLORER_SEARCH_MODES)
    started = perf_counter()
    with _content_free_span(
        "explorer search", SpanKind.INTERNAL, {"dwhnavigator.explorer.mode": bounded_mode}
    ) as span:
        try:
            yield record
        finally:
            span.set_attribute("dwhnavigator.explorer.results", record.results)
            _signals.instruments.explorer_search_duration.record(
                perf_counter() - started, {"mode": bounded_mode}
            )
