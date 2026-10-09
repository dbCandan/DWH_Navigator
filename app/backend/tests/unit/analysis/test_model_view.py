"""An analysis job's view of the model port (question-analysis Requirement 5, 11, 24): the call
runs on the event loop, its summary and events go to the trace without content, a failure is the
port's class, a stop is ``Cancelled`` and never a failure."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.llm import (
    AdaptedFeature,
    CancelSignal,
    LlmCallSummary,
    LlmChatRequest,
    LlmChatResult,
    LlmConnection,
    LlmModelList,
    LlmOutcome,
    LlmProbeResult,
    LlmPurpose,
    ProbeOperation,
)
from app.services.analysis import cancel, trace
from app.services.analysis.llm.port import FailureCode, ModelFailure
from app.services.analysis.model_view import JobModel, sampling_of

pytestmark = pytest.mark.unit

CONNECTION = LlmConnection(endpoint="http://10.0.0.5:8000/v1", chat_model="m", public_id="i-1")


def _summary(outcome: LlmOutcome, **over: Any) -> LlmCallSummary:
    values: dict[str, Any] = {
        "purpose": LlmPurpose.ANALYSIS,
        "integration_public_id": "i-1",
        "model": "m",
        "started_at": datetime.now(UTC),
        "wait_ms": 0,
        "duration_ms": 5,
        "outcome": outcome,
        "http_status": None,
        "requests": 1,
        "adaptations": (),
        "repaired": False,
        "prompt_tokens": 10,
        "completion_tokens": 4,
    }
    return LlmCallSummary(**(values | over))


class FakePort:
    def __init__(self) -> None:
        self.answer: Callable[[CancelSignal | None], Any] = lambda _c: LlmChatResult(
            LlmOutcome.OK, _summary(LlmOutcome.OK), {"ok": True}
        )
        self.probe = LlmProbeResult(ProbeOperation.HEALTH, LlmOutcome.OK, 200, 3)
        self.requests: list[LlmChatRequest] = []

    async def chat(
        self, connection: LlmConnection, request: LlmChatRequest, *, cancel: Any = None
    ) -> LlmChatResult:
        self.requests.append(request)
        result = self.answer(cancel)
        if asyncio.iscoroutine(result):
            result = await result
        assert isinstance(result, LlmChatResult)
        return result

    async def health(self, connection: LlmConnection) -> LlmProbeResult:
        return self.probe

    async def list_models(self, connection: LlmConnection, **_: Any) -> LlmModelList:
        raise NotImplementedError


async def _in_thread(port: FakePort, connection: Any, work: Callable[[JobModel], Any],
                     token: cancel.Token | None = None) -> tuple[Any, trace.Trace]:  # fmt: skip
    token = token or cancel.Token()
    model = JobModel(port, connection, asyncio.get_running_loop(), token, "a-1")

    def run() -> tuple[Any, trace.Trace]:
        with trace.recording() as tr, cancel.using(token), trace.span("adım", key="shortlist"):
            try:
                return work(model), tr
            except cancel.Cancelled:
                return "stopped", tr

    return await asyncio.to_thread(run)


async def test_a_call_carries_its_summary_and_tokens() -> None:
    port = FakePort()
    value, tr = await _in_thread(
        port, CONNECTION, lambda m: m.chat_json("s", "u", {}, max_tokens=9)
    )
    assert value == {"ok": True}
    spans = tr.to_list()
    call = next(s for s in spans if s["kind"] == "llm")
    assert call["name"] == "LLM çağrısı" and call["data"]["call"]["outcome"] == "ok"
    assert call["data"]["prompt_tokens"] == 10 and tr.totals()["llm_calls"] == 1
    request = port.requests[0]
    assert (request.max_tokens, request.purpose, request.analysis_public_id) == (
        9, LlmPurpose.ANALYSIS, "a-1"
    )  # fmt: skip


async def test_adaptations_and_repair_are_events_without_content() -> None:
    port = FakePort()
    summary = _summary(
        LlmOutcome.OK,
        adaptations=(AdaptedFeature.RESPONSE_FORMAT, AdaptedFeature.SEED),
        repaired=True,
    )
    port.answer = lambda _c: LlmChatResult(LlmOutcome.OK, summary, {"ok": True})
    _value, tr = await _in_thread(port, CONNECTION, lambda m: m.chat_json("s", "u", {}))
    events = [(s["name"], s.get("detail")) for s in tr.to_list() if s["kind"] == "event"]
    assert events == [
        ("Model bir özelliği reddetti — onsuz yeniden", "response_format"),
        ("Model bir özelliği reddetti — onsuz yeniden", "seed"),
        ("Yanıt JSON değil — onarım isteniyor", "deneme 1"),
    ]


@pytest.mark.parametrize(
    ("outcome", "status", "failure"),
    [
        (LlmOutcome.TIMEOUT, None, ModelFailure(FailureCode.TIMEOUT)),
        (LlmOutcome.CONTEXT_EXCEEDED, 400, ModelFailure(FailureCode.CONTEXT_EXCEEDED, 400)),
        (LlmOutcome.UPSTREAM_STATUS, 502, ModelFailure(FailureCode.UPSTREAM_STATUS, 502)),
        (LlmOutcome.INVALID_JSON, 200, ModelFailure(FailureCode.INVALID_JSON, 200)),
    ],
)
async def test_a_failure_is_the_ports_class(
    outcome: LlmOutcome, status: int | None, failure: ModelFailure
) -> None:
    port = FakePort()
    port.answer = lambda _c: LlmChatResult(
        outcome, _summary(outcome, http_status=status), None, http_status=status
    )
    holder: dict[str, Any] = {}

    def work(m: JobModel) -> Any:
        reply = m.chat_json("s", "u", {})
        holder["failure"] = m.last_failure
        return reply

    value, tr = await _in_thread(port, CONNECTION, work)
    assert value is None and holder["failure"] == failure
    call = next(s for s in tr.to_list() if s["kind"] == "llm")
    assert call["status"] == "error" and call["detail"] == f"m — {outcome.value}"


async def test_a_stop_closes_the_call_and_raises_cancelled() -> None:
    port = FakePort()
    token = cancel.Token()

    async def hanging(signal: Any) -> LlmChatResult:
        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        signal.on_cancel(lambda: loop.call_soon_threadsafe(stopped.set))
        await stopped.wait()
        return LlmChatResult(LlmOutcome.CANCELLED, _summary(LlmOutcome.CANCELLED), None)

    port.answer = hanging
    asyncio.get_running_loop().call_later(0.1, token.cancel)
    value, tr = await _in_thread(port, CONNECTION, lambda m: m.chat_json("s", "u", {}), token)
    assert value == "stopped"
    assert next(s for s in tr.to_list() if s["kind"] == "llm")["status"] == "error"


async def test_without_a_usable_connection_nothing_is_sent() -> None:
    port = FakePort()
    none, _ = await _in_thread(port, LlmOutcome.NOT_CONFIGURED, lambda m: (m.available, m.health()))
    assert none == (False, ModelFailure(FailureCode.NOT_CONFIGURED))
    key, _ = await _in_thread(port, LlmOutcome.KEY_UNREADABLE, lambda m: (m.available, m.health()))
    assert key == (True, ModelFailure(FailureCode.KEY_UNREADABLE))
    assert port.requests == []
    assert sampling_of(LlmOutcome.NOT_CONFIGURED).model == ""
    assert sampling_of(CONNECTION).model == "m"


async def test_the_server_check_is_kept_on_its_step() -> None:
    port = FakePort()
    port.probe = LlmProbeResult(ProbeOperation.HEALTH, LlmOutcome.UNAUTHORIZED, 401, 4, cached=True)
    value, tr = await _in_thread(port, CONNECTION, lambda m: m.health())
    assert value == ModelFailure(FailureCode.UNAUTHORIZED, 401)
    step = tr.to_list()[0]
    assert step["data"]["check"] == {
        "outcome": "unauthorized", "http_status": 401, "duration_ms": 4, "cached": True
    }  # fmt: skip
