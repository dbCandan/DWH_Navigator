"""httpx adapter of the model port (data-dictionary 003-llm-connection Decision 1, 2, 5 and 6).

A chat call is the source client's ``OpenAICompatibleClient._chat_json``: the request body is
written with ``json.dumps`` defaults and sent as ready bytes, a 400 refusal drops one feature and
resends (at most three times, learned per connection), and a reply without a JSON object earns one
repair request. On top of the source: only private addresses, verified TLS without proxies or
redirects, a 4 MiB response limit, the process-wide slot limit, fixed failure classes, a stop that
closes the open request, and one content-free summary, log event, span and metric set per call.
No prompt, schema, reply, server error text, address or key is logged, traced or summarized.
"""

import asyncio
import errno
import json
import logging
import math
import ssl
import threading
import time
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpcore
import httpx

from app.core import telemetry
from app.core.logging import log_event
from app.domain.llm import (
    CONNECT_TIMEOUT_SECONDS,
    ERROR_TEXT_CHARS,
    HEALTH_TIMEOUT_SECONDS,
    HEALTH_TTL_SECONDS,
    INVENTORY_BUDGET_SECONDS,
    INVENTORY_PARALLEL,
    INVENTORY_SERVER_BUDGET_SECONDS,
    INVENTORY_TIMEOUT_SECONDS,
    LM_STUDIO_TIMEOUT_SECONDS,
    MAX_ADAPTATIONS,
    MAX_REPLIES,
    MAX_RESPONSE_BYTES,
    MODEL_LIST_BUDGET_SECONDS,
    MODEL_LIST_TIMEOUT_SECONDS,
    REPAIR_PROMPT,
    REPAIR_REPLY_CHARS,
    TEST_CHAT_BUDGET_SECONDS,
    TEST_CHAT_TIMEOUT_SECONDS,
    USER_AGENT,
    AdaptedFeature,
    CancelSignal,
    LlmCallSummary,
    LlmChatPort,
    LlmChatRequest,
    LlmChatResult,
    LlmConnection,
    LlmModelInfo,
    LlmModelList,
    LlmOutcome,
    LlmProbeResult,
    LlmPurpose,
    ProbeOperation,
    context_exceeded,
    endpoint_url,
    lm_studio_models_url,
    parse_json_reply,
    refused_feature,
)
from app.domain.turkish_text import fold
from app.infrastructure.llm.call_slots import CallSlots
from app.infrastructure.llm.network import (
    HostUnresolved,
    NetworkPolicyDenied,
    PolicyTransport,
    PrivateNetworkBackend,
    Resolver,
    resolve_private,
    system_resolver,
    tls_context,
)

logger = logging.getLogger("app.llm")
# httpx logs every request with its full URL at INFO and httpcore traces connections at DEBUG; the
# model server's address must not reach the application log (Requirement 22).
for _library in ("httpx", "httpcore"):
    logging.getLogger(_library).setLevel(logging.WARNING)

Message = dict[str, str]


@dataclass(frozen=True, slots=True)
class LlmTimeouts:
    """Requirement 9 times in seconds; tests shorten them, the application uses the defaults."""

    connect: float = CONNECT_TIMEOUT_SECONDS
    health: float = HEALTH_TIMEOUT_SECONDS
    health_ttl: float = HEALTH_TTL_SECONDS
    model_list: float = MODEL_LIST_TIMEOUT_SECONDS
    model_list_budget: float = MODEL_LIST_BUDGET_SECONDS
    lm_studio: float = LM_STUDIO_TIMEOUT_SECONDS
    inventory: float = INVENTORY_TIMEOUT_SECONDS
    inventory_server_budget: float = INVENTORY_SERVER_BUDGET_SECONDS
    inventory_budget: float = INVENTORY_BUDGET_SECONDS
    test_chat: float = TEST_CHAT_TIMEOUT_SECONDS
    test_chat_budget: float = TEST_CHAT_BUDGET_SECONDS


@dataclass(slots=True)
class RequestFeatures:
    """What a chat request still sends; a feature the server refused is dropped (Requirement 7)."""

    system_role: bool
    structured: bool
    reasoning_effort: str
    seed: int | None

    @classmethod
    def initial(cls, connection: LlmConnection) -> "RequestFeatures":
        seed = connection.seed if connection.seed >= 0 else None
        return cls(True, True, connection.reasoning_effort, seed)

    def refused(self, folded_error: str) -> AdaptedFeature | None:
        return refused_feature(
            folded_error,
            system_role=self.system_role,
            structured=self.structured,
            reasoning_effort=self.reasoning_effort,
            seed=self.seed,
        )

    def drop(self, feature: AdaptedFeature) -> None:
        if feature is AdaptedFeature.SYSTEM_ROLE:
            self.system_role = False
        elif feature is AdaptedFeature.RESPONSE_FORMAT:
            self.structured = False
        elif feature is AdaptedFeature.REASONING_EFFORT:
            self.reasoning_effort = ""
        else:
            self.seed = None


def chat_body(
    *,
    model: str,
    messages: Sequence[Message],
    system: str,
    temperature: float,
    max_tokens: int,
    schema: Mapping[str, Any],
    features: RequestFeatures,
) -> bytes:
    """The request body bytes, field for field and byte for byte as the source writes them."""

    sent = list(messages)
    if not features.system_role:  # fold the instructions into the first user turn
        first = {"role": "user", "content": f"{system}\n\n{sent[1]['content']}"}
        sent = [first, *sent[2:]]
    body: dict[str, Any] = {
        "model": model,
        "messages": sent,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if features.reasoning_effort:
        body["reasoning_effort"] = features.reasoning_effort
    if features.seed is not None:
        body["seed"] = features.seed
    if features.structured:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "result", "strict": True, "schema": dict(schema)},
        }
    # Decision 6: json.dumps defaults (ASCII escapes, ", " and ": "), never httpx's own writer.
    return json.dumps(body).encode("utf-8")


class _Failure(Exception):
    def __init__(self, outcome: LlmOutcome) -> None:
        super().__init__(outcome.value)
        self.outcome = outcome


def _chain(error: BaseException) -> list[BaseException]:
    """The error, its causes and contexts, and the members of exception groups among them."""

    seen: set[int] = set()
    found: list[BaseException] = []
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        found.append(current)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return found


def classify_transport_error(error: BaseException) -> LlmOutcome:
    """The Requirement 13 class of an error raised while connecting, sending or reading."""

    if isinstance(error, _Failure):
        return error.outcome
    if isinstance(error, NetworkPolicyDenied):
        return LlmOutcome.NETWORK_POLICY_DENIED
    if isinstance(error, HostUnresolved):
        return LlmOutcome.NAME_UNRESOLVED
    if isinstance(error, (httpx.TimeoutException, httpcore.TimeoutException, TimeoutError)):
        return LlmOutcome.TIMEOUT
    if isinstance(error, httpx.DecodingError):
        return LlmOutcome.INVALID_RESPONSE
    if isinstance(error, (httpx.TransportError, httpcore.NetworkError, OSError)):
        chain = _chain(error)
        if any(isinstance(item, ssl.SSLError) for item in chain):
            return LlmOutcome.TLS_ERROR
        if any(
            isinstance(item, ConnectionRefusedError)
            or getattr(item, "errno", None) == errno.ECONNREFUSED
            for item in chain
        ):
            return LlmOutcome.CONNECT_REFUSED
        return LlmOutcome.CONNECT_ERROR
    raise error


def _error_text(raw: bytes) -> str:
    """The first 600 characters of a refusal body; read for classification only, never kept."""

    return raw.decode("utf-8", "replace")[:ERROR_TEXT_CHARS]


def _status_outcome(status: int, raw: bytes) -> LlmOutcome:
    if status in (401, 403):
        return LlmOutcome.UNAUTHORIZED
    if context_exceeded(fold(_error_text(raw))):
        return LlmOutcome.CONTEXT_EXCEEDED
    return LlmOutcome.UPSTREAM_STATUS


def _json_object(raw: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _usage(data: Mapping[str, Any], name: str) -> int:
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        return 0
    try:
        return int(usage.get(name) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _message_content(data: Mapping[str, Any]) -> str | None:
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(message, dict):
        return None
    return str(message.get("content") or "")


def _context_length(value: object) -> int | None:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return int(value) if isinstance(value, int | float) else None


def _models(data: Mapping[str, Any], rich: Mapping[str, Mapping[str, Any]]) -> list[LlmModelInfo]:
    """Requirement 14: one row per ``data[]`` item, with LM Studio's details when it gave them."""

    items = data.get("data", [])
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise _Failure(LlmOutcome.INVALID_RESPONSE)
    rows: list[LlmModelInfo] = []
    for item in items:
        model_id = str(item.get("id", ""))
        extra = rich.get(model_id, {})
        context = (
            extra.get("max_context_length")
            or item.get("max_model_len")
            or item.get("context_length")
            or item.get("context_window")
        )
        rows.append(
            LlmModelInfo(
                id=model_id,
                type=str(extra.get("type", "")),
                loaded=(extra.get("state") == "loaded") if extra else None,
                context=_context_length(context),
                owner=str(item.get("owned_by", "") or extra.get("publisher", "")),
                quant=str(extra.get("quantization", "")),
            )
        )
    return rows


def _authorization(connection: LlmConnection) -> dict[str, str]:
    # Requirement 6 and 12: the header exists only when the connection has a key.
    return {"Authorization": f"Bearer {connection.api_key}"} if connection.api_key else {}


def _ms(seconds: float) -> int:
    return max(0, round(seconds * 1000))


@dataclass(slots=True)
class _CallState:
    """Counters of one chat call; the parsed reply is the only content it holds."""

    wait_ms: int = 0
    http_status: int | None = None
    requests: int = 0
    adaptations: list[AdaptedFeature] = field(default_factory=list)
    repaired: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    value: dict[str, Any] | None = None


class OpenAICompatibleAdapter:
    """The process's single model adapter: slots, learned features and health results."""

    def __init__(
        self,
        *,
        ca_bundle: str,
        max_concurrent_calls: int,
        resolver: Resolver = system_resolver,
        timeouts: LlmTimeouts | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ssl_context = tls_context(ca_bundle)
        self._slots = CallSlots(max_concurrent_calls)
        self._resolver = resolver
        self._timeouts = timeouts or LlmTimeouts()
        self._clock = clock
        self._lock = threading.Lock()
        # Keyed by integration (or fingerprint without one); a changed connection starts afresh.
        self._features: dict[str, tuple[str, RequestFeatures]] = {}
        self._health: dict[str, tuple[str, float, LlmProbeResult]] = {}

    @asynccontextmanager
    async def _client(self, *, read: float, connect: float) -> AsyncIterator[httpx.AsyncClient]:
        transport = PolicyTransport(
            ssl_context=self._ssl_context,
            network_backend=PrivateNetworkBackend(self._resolver),
        )
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(read, connect=min(self._timeouts.connect, connect)),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            yield client

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> tuple[int, bytes]:
        request = client.build_request(
            method,
            url,
            headers=dict(headers),
            content=body,
            timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
        )
        response = await client.send(request, stream=True)
        try:
            received = bytearray()
            async for chunk in response.aiter_bytes():
                received.extend(chunk)
                if len(received) > MAX_RESPONSE_BYTES:
                    raise _Failure(LlmOutcome.RESPONSE_TOO_LARGE)
        finally:
            await response.aclose()
        return response.status_code, bytes(received)

    async def check_address(self, endpoint: str) -> LlmOutcome:
        """Requirement 2 on save: the host resolves and every address is private."""

        parts = urlsplit(endpoint)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            await resolve_private(
                self._resolver, parts.hostname or "", port, timeout=self._timeouts.connect
            )
        except NetworkPolicyDenied:
            return LlmOutcome.NETWORK_POLICY_DENIED
        except (HostUnresolved, httpcore.ConnectTimeout):
            return LlmOutcome.NAME_UNRESOLVED
        return LlmOutcome.OK

    # --- chat --------------------------------------------------------------------------------

    def _learned(self, connection: LlmConnection) -> RequestFeatures:
        key = connection.public_id or connection.fingerprint
        fingerprint = connection.fingerprint
        with self._lock:
            entry = self._features.get(key)
            if entry is None or entry[0] != fingerprint:
                entry = (fingerprint, RequestFeatures.initial(connection))
                self._features[key] = entry
            return entry[1]

    async def chat(
        self,
        connection: LlmConnection,
        request: LlmChatRequest,
        *,
        cancel: CancelSignal | None = None,
    ) -> LlmChatResult:
        testing = request.purpose is LlmPurpose.CONNECTION_TEST
        # A connection test starts from nothing learned and teaches the analyses nothing.
        features = RequestFeatures.initial(connection) if testing else self._learned(connection)
        read_timeout = float(connection.timeout_seconds)
        budget: float | None = None
        if testing:
            read_timeout = min(read_timeout, self._timeouts.test_chat)
            budget = self._timeouts.test_chat_budget
        started_at = datetime.now(UTC)
        started = self._clock()
        state = _CallState()
        with telemetry.llm_chat_span(request.purpose.value) as record:
            work = self._call(connection, request, features, state, read_timeout, budget)
            try:
                outcome = await self._cancellable(work, cancel)
            except asyncio.CancelledError:
                self._finish(connection, request, state, LlmOutcome.CANCELLED, started, started_at)
                record.outcome = LlmOutcome.CANCELLED.value
                raise
            summary = self._finish(connection, request, state, outcome, started, started_at)
            record.outcome = outcome.value
            record.http_status = state.http_status
            record.requests = state.requests
            record.adaptations = len(state.adaptations)
            record.repaired = state.repaired
        ok = outcome is LlmOutcome.OK
        return LlmChatResult(
            outcome=outcome,
            summary=summary,
            value=state.value if ok else None,
            http_status=state.http_status,
        )

    @staticmethod
    async def _cancellable(
        work: Coroutine[Any, Any, LlmOutcome], cancel: CancelSignal | None
    ) -> LlmOutcome:
        """Run ``work``; a stop of the analysis closes it at once and makes it ``cancelled``."""

        if cancel is None:
            return await work
        if cancel.cancelled:
            work.close()
            return LlmOutcome.CANCELLED
        loop = asyncio.get_running_loop()
        inner = loop.create_task(work)

        def stop() -> None:
            # The stop may come from the analysis engine's own thread.
            try:
                loop.call_soon_threadsafe(inner.cancel)
            except RuntimeError:  # the event loop is already closed
                pass

        unregister = cancel.on_cancel(stop)
        try:
            return await inner
        except asyncio.CancelledError:
            current = asyncio.current_task()
            caller_cancelled = current is not None and current.cancelling() > 0
            if inner.cancelled() and cancel.cancelled and not caller_cancelled:
                return LlmOutcome.CANCELLED
            raise
        finally:
            unregister()

    async def _call(
        self,
        connection: LlmConnection,
        request: LlmChatRequest,
        features: RequestFeatures,
        state: _CallState,
        read_timeout: float,
        budget: float | None,
    ) -> LlmOutcome:
        try:
            async with asyncio.timeout(budget):
                waited = self._clock()
                telemetry.llm_waiting_changed(1)
                try:
                    await self._slots.acquire()
                finally:
                    telemetry.llm_waiting_changed(-1)
                    state.wait_ms = _ms(self._clock() - waited)
                telemetry.llm_inflight_changed(1)
                try:
                    return await self._exchange(connection, request, features, state, read_timeout)
                finally:
                    telemetry.llm_inflight_changed(-1)
                    self._slots.release()
        except TimeoutError:  # the test step's ceiling, slot wait included (Requirement 15)
            return LlmOutcome.TIMEOUT

    async def _exchange(
        self,
        connection: LlmConnection,
        request: LlmChatRequest,
        features: RequestFeatures,
        state: _CallState,
        read_timeout: float,
    ) -> LlmOutcome:
        url = endpoint_url(connection.endpoint, "/chat/completions")
        headers = {"Content-Type": "application/json", **_authorization(connection)}
        messages: list[Message] = [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ]
        replies = adaptations = 0
        try:
            async with self._client(read=read_timeout, connect=read_timeout) as client:
                while replies < MAX_REPLIES:
                    body = chat_body(
                        model=connection.chat_model,
                        messages=messages,
                        system=request.system,
                        temperature=connection.temperature,
                        max_tokens=request.max_tokens,
                        schema=request.schema,
                        features=features,
                    )
                    state.requests += 1
                    state.http_status = None
                    status, raw = await self._send(client, "POST", url, headers, body)
                    state.http_status = status
                    if status == 400 and adaptations < MAX_ADAPTATIONS:
                        refused = features.refused(fold(_error_text(raw)))
                        if refused is not None:
                            # Requirement 7: the same request again, without the refused feature.
                            features.drop(refused)
                            adaptations += 1
                            state.adaptations.append(refused)
                            telemetry.record_llm_adaptation(refused.value)
                            continue
                    if not 200 <= status < 300:
                        return _status_outcome(status, raw)
                    data = _json_object(raw)
                    if data is None:
                        return LlmOutcome.INVALID_RESPONSE
                    state.prompt_tokens += _usage(data, "prompt_tokens")
                    state.completion_tokens += _usage(data, "completion_tokens")
                    content = _message_content(data)
                    if content is None:
                        return LlmOutcome.INVALID_RESPONSE
                    replies += 1
                    parsed = parse_json_reply(content)
                    if parsed is not None:
                        state.value = parsed
                        return LlmOutcome.OK
                    # Requirement 8: one repair request with the start of the invalid reply.
                    state.repaired = True
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content[:REPAIR_REPLY_CHARS]},
                        {"role": "user", "content": REPAIR_PROMPT},
                    ]
                return LlmOutcome.INVALID_JSON
        except Exception as error:  # noqa: BLE001 - classify re-raises what it does not know
            return classify_transport_error(error)

    def _finish(
        self,
        connection: LlmConnection,
        request: LlmChatRequest,
        state: _CallState,
        outcome: LlmOutcome,
        started: float,
        started_at: datetime,
    ) -> LlmCallSummary:
        duration = self._clock() - started
        summary = LlmCallSummary(
            purpose=request.purpose,
            integration_public_id=connection.public_id,
            model=connection.chat_model,
            started_at=started_at,
            wait_ms=state.wait_ms,
            duration_ms=_ms(duration),
            outcome=outcome,
            http_status=state.http_status,
            requests=state.requests,
            adaptations=tuple(state.adaptations),
            repaired=state.repaired,
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
        )
        telemetry.record_llm_call(
            purpose=request.purpose.value,
            outcome=outcome.value,
            duration_seconds=duration,
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
        )
        log_event(
            logger,
            "llm.call",
            purpose=request.purpose.value,
            integration_public_id=connection.public_id,
            model=connection.chat_model,
            outcome=outcome.value,
            http_status=state.http_status,
            requests=state.requests,
            adaptations=",".join(feature.value for feature in state.adaptations),
            repaired=state.repaired,
            wait_ms=state.wait_ms,
            duration_ms=summary.duration_ms,
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
            analysis_public_id=request.analysis_public_id,
        )
        return summary

    # --- /models reads -----------------------------------------------------------------------

    async def health(self, connection: LlmConnection) -> LlmProbeResult:
        key = connection.public_id or connection.fingerprint
        fingerprint = connection.fingerprint
        now = self._clock()
        with self._lock:
            entry = self._health.get(key)
        if (
            entry is not None
            and entry[0] == fingerprint
            and now - entry[1] < self._timeouts.health_ttl
        ):
            cached = replace(entry[2], duration_ms=0, cached=True)
            with telemetry.llm_probe_span(ProbeOperation.HEALTH.value) as record:
                record.outcome = cached.outcome.value
                record.cached = True
            self._observe_probe(connection, cached)
            return cached
        listing = await self._read_models(
            connection,
            ProbeOperation.HEALTH,
            request_timeout=self._timeouts.health,
            budget=self._timeouts.health,
            details=False,
        )
        with self._lock:
            self._health[key] = (fingerprint, now, listing.probe)
        return listing.probe

    async def list_models(
        self,
        connection: LlmConnection,
        *,
        operation: ProbeOperation = ProbeOperation.MODELS,
        details: bool = True,
    ) -> LlmModelList:
        if operation is ProbeOperation.INVENTORY:
            request_timeout = self._timeouts.inventory
            budget = self._timeouts.inventory_server_budget
        elif operation is ProbeOperation.HEALTH:
            request_timeout = budget = self._timeouts.health
        else:
            request_timeout = self._timeouts.model_list
            budget = self._timeouts.model_list_budget
        return await self._read_models(
            connection,
            operation,
            request_timeout=request_timeout,
            budget=budget,
            details=details,
        )

    async def list_models_of(self, connections: Sequence[LlmConnection]) -> list[LlmModelList]:
        """The inventory: every server, at most eight at once, within 50 s in total."""

        deadline = self._clock() + self._timeouts.inventory_budget
        parallel = asyncio.Semaphore(INVENTORY_PARALLEL)

        async def one(connection: LlmConnection) -> LlmModelList:
            started = self._clock()
            try:
                async with asyncio.timeout(max(0.0, deadline - self._clock())):
                    await parallel.acquire()
            except TimeoutError:
                probe = LlmProbeResult(
                    ProbeOperation.INVENTORY,
                    LlmOutcome.TIMEOUT,
                    None,
                    _ms(self._clock() - started),
                )
                self._observe_probe(connection, probe)
                return LlmModelList(probe)
            try:
                return await self._read_models(
                    connection,
                    ProbeOperation.INVENTORY,
                    request_timeout=self._timeouts.inventory,
                    budget=max(
                        0.0,
                        min(self._timeouts.inventory_server_budget, deadline - self._clock()),
                    ),
                    details=True,
                )
            finally:
                parallel.release()

        return list(await asyncio.gather(*(one(connection) for connection in connections)))

    async def _lm_studio(
        self, client: httpx.AsyncClient, url: str, connection: LlmConnection
    ) -> dict[str, Mapping[str, Any]]:
        """LM Studio's per-model details; any failure only means there are none (Requirement 14)."""

        try:
            async with asyncio.timeout(self._timeouts.lm_studio):
                status, raw = await self._send(
                    client,
                    "GET",
                    url,
                    _authorization(connection),
                    timeout=httpx.Timeout(self._timeouts.lm_studio),
                )
        except Exception:  # noqa: BLE001 - the detail list is optional
            return {}
        data = _json_object(raw) if 200 <= status < 300 else None
        items = data.get("data") if data is not None else None
        if not isinstance(items, list):
            return {}
        return {str(item.get("id")): item for item in items if isinstance(item, dict)}

    async def _read_models(
        self,
        connection: LlmConnection,
        operation: ProbeOperation,
        *,
        request_timeout: float,
        budget: float,
        details: bool,
    ) -> LlmModelList:
        started = self._clock()
        http_status: int | None = None
        models: list[LlmModelInfo] = []
        with telemetry.llm_probe_span(operation.value) as record:
            try:
                async with asyncio.timeout(budget):
                    async with self._client(read=request_timeout, connect=budget) as client:
                        rich: dict[str, Mapping[str, Any]] = {}
                        lm_studio = lm_studio_models_url(connection.endpoint) if details else None
                        if lm_studio is not None:
                            rich = await self._lm_studio(client, lm_studio, connection)
                        status, raw = await self._send(
                            client,
                            "GET",
                            endpoint_url(connection.endpoint, "/models"),
                            _authorization(connection),
                        )
                        http_status = status
                        if not 200 <= status < 300:
                            outcome = _status_outcome(status, raw)
                        else:
                            data = _json_object(raw)
                            if data is None:
                                outcome = LlmOutcome.INVALID_RESPONSE
                            else:
                                models = _models(data, rich)
                                outcome = LlmOutcome.OK
            except Exception as error:  # noqa: BLE001 - classify re-raises what it does not know
                outcome = classify_transport_error(error)
                models = []
            record.outcome = outcome.value
        probe = LlmProbeResult(operation, outcome, http_status, _ms(self._clock() - started))
        self._observe_probe(connection, probe)
        return LlmModelList(probe, tuple(models))

    def _observe_probe(self, connection: LlmConnection, probe: LlmProbeResult) -> None:
        telemetry.record_llm_probe(operation=probe.operation.value, outcome=probe.outcome.value)
        log_event(
            logger,
            "llm.probe",
            operation=probe.operation.value,
            integration_public_id=connection.public_id,
            outcome=probe.outcome.value,
            http_status=probe.http_status,
            duration_ms=probe.duration_ms,
            cached=probe.cached,
        )


if TYPE_CHECKING:

    def _implements_port(adapter: OpenAICompatibleAdapter) -> LlmChatPort:
        return adapter
