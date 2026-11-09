"""One analysis job's view of the model port (question-analysis Requirement 24, Decision 15).

The engine runs in its own thread and speaks the source's synchronous ``LLMClient`` contract. This
view hands each call to the llm-connection port on the application's event loop
(``asyncio.run_coroutine_threadsafe``) and waits for it. The view belongs to one job: the connection
snapshot read when the job started (llm-connection Requirement 5), the job's stop token and the last
failure class stay with it, so no failure leaks between analyses.

Every chat call is one ``LLM çağrısı`` step of the job's trace carrying the port's content-free call
summary; a dropped request feature and a repair request become events that carry only the feature's
name and the attempt number (analysis-records Requirement 4). A stopped job's call ends as
``cancelled`` and raises ``Cancelled``: a stop is never a model failure.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Mapping
from typing import Any

from app.domain.llm import (
    LlmChatPort,
    LlmChatRequest,
    LlmConnection,
    LlmOutcome,
    LlmProbeResult,
    LlmPurpose,
)
from app.services.analysis import cancel, trace
from app.services.analysis.llm.port import FailureCode, ModelFailure, ModelSampling

# How often a thread waiting on the event loop looks at the job's stop token.
STOP_POLL_SECONDS = 0.1
REFUSED_EVENT = "Model bir özelliği reddetti — onsuz yeniden"
REPAIR_EVENT = "Yanıt JSON değil — onarım isteniyor"


def failure_of(outcome: LlmOutcome, http_status: int | None = None) -> ModelFailure:
    return ModelFailure(FailureCode(outcome.value), http_status)


def sampling_of(connection: LlmConnection | LlmOutcome) -> ModelSampling:
    """The saved-answer fingerprint's model fields; without a usable connection there is no
    model, so no saved answer can match (none is ever written without one)."""

    if isinstance(connection, LlmConnection):
        model, temperature, effort, seed = connection.sampling
        return ModelSampling(model, temperature, effort, seed)
    return ModelSampling("", 0.0, "", 0)


class JobModel:
    """``LLMClient`` of one analysis job over the llm-connection port."""

    def __init__(
        self,
        port: LlmChatPort,
        connection: LlmConnection | LlmOutcome,
        loop: asyncio.AbstractEventLoop,
        token: cancel.Token,
        analysis_public_id: str,
    ) -> None:
        self._port = port
        self._connection = connection
        self._loop = loop
        self._token = token
        self._analysis_public_id = analysis_public_id
        self._last_failure: ModelFailure | None = None
        self._last_partial: dict[str, Any] | None = None

    @property
    def available(self) -> bool:
        # An unreadable key still counts as connected: the server check names the reason.
        return self._connection is not LlmOutcome.NOT_CONFIGURED

    @property
    def model(self) -> str:
        return self._connection.chat_model if isinstance(self._connection, LlmConnection) else ""

    @property
    def last_failure(self) -> ModelFailure | None:
        return self._last_failure

    @property
    def last_partial(self) -> dict[str, Any] | None:
        """The last call's reply when it was cut at max_tokens, closed after its last whole
        element; None otherwise. Only a step that can work with a part reads it."""
        return self._last_partial

    def _wait(self, future: concurrent.futures.Future[Any]) -> Any:
        """The call's result; a stop of the job abandons a call that does not end by itself."""

        while True:
            try:
                return future.result(timeout=STOP_POLL_SECONDS)
            except concurrent.futures.TimeoutError:
                if self._token.cancelled:
                    future.cancel()
                    raise cancel.Cancelled from None

    def health(self) -> ModelFailure | None:
        connection = self._connection
        if not isinstance(connection, LlmConnection):
            return failure_of(connection)
        cancel.check()
        future = asyncio.run_coroutine_threadsafe(self._port.health(connection), self._loop)
        probe: LlmProbeResult = self._wait(future)
        step = trace.current()
        if step is not None:
            step.data["check"] = {
                "outcome": probe.outcome.value,
                "http_status": probe.http_status,
                "duration_ms": probe.duration_ms,
                "cached": probe.cached,
            }
        return None if probe.ok else failure_of(probe.outcome, probe.http_status)

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        connection = self._connection
        self._last_partial = None
        if not isinstance(connection, LlmConnection):
            self._last_failure = failure_of(connection)
            return None
        cancel.check()
        with trace.span("LLM çağrısı", connection.chat_model, trace.LLM) as step:
            request = LlmChatRequest(
                system=system,
                user=user,
                schema=schema,
                max_tokens=max_tokens,
                purpose=LlmPurpose.ANALYSIS,
                analysis_public_id=self._analysis_public_id,
            )
            future = asyncio.run_coroutine_threadsafe(
                self._port.chat(connection, request, cancel=self._token), self._loop
            )
            result = self._wait(future)
            summary = result.summary
            trace.count(
                requests=summary.requests,
                prompt_tokens=summary.prompt_tokens,
                completion_tokens=summary.completion_tokens,
            )
            if step is not None:
                step.data["call"] = summary.as_dict()
            for feature in summary.adaptations:
                trace.event(REFUSED_EVENT, feature.value)
            if summary.repaired:
                trace.event(REPAIR_EVENT, "deneme 1")
            if result.outcome is LlmOutcome.CANCELLED or self._token.cancelled:
                raise cancel.Cancelled
            if not result.ok:
                self._last_failure = failure_of(result.outcome, result.http_status)
                self._last_partial = result.partial
                if step is not None:
                    step.status = "error"
                    step.detail = f"{connection.chat_model} — {result.outcome.value}"
                return None
            self._last_failure = None
            value: dict[str, Any] | None = result.value
            return value
