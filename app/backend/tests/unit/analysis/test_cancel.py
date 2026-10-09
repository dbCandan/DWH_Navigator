"""Stopping an analysis: waits end and the hooks run (the model adapter's connection cut is
tested with that adapter, llm-connection)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from app.services.analysis import cancel

pytestmark = pytest.mark.unit


def wait(seconds: float) -> None:
    """A long step that ends (raising ``Cancelled``) as soon as the analysis is stopped."""
    token = cancel.current()
    if token is not None and token.wait(seconds):
        raise cancel.Cancelled


def test_no_token_is_a_no_op() -> None:
    cancel.check()
    wait(0)
    assert cancel.current() is None


def test_token_runs_hooks_and_ends_waits() -> None:
    token = cancel.Token()
    ran: list[str] = []
    token.on_cancel(lambda: ran.append("a"))
    off = token.on_cancel(lambda: ran.append("b"))
    off()
    threading.Timer(0.1, token.cancel).start()
    started = time.perf_counter()
    with cancel.using(token), pytest.raises(cancel.Cancelled):
        wait(10)
    assert time.perf_counter() - started < 2
    assert ran == ["a"]
    token.on_cancel(lambda: ran.append("late"))  # already stopped: runs at once
    assert ran == ["a", "late"]
    token.cancel()  # idempotent
    assert ran == ["a", "late"]


def test_stopped_analysis_does_not_fall_back() -> None:
    """A stop during a model call ends the analysis with ``Cancelled``: no "Analiz
    yapılamadı" answer and no rule answer in its place (Requirement 11)."""
    from tests.unit.analysis.test_analyst import SHORTLIST, ScriptedClient, engine

    token = cancel.Token()

    class StoppedClient(ScriptedClient):
        def chat_json(self, system: str, user: str, schema: Any, *, max_tokens: int = 1024) -> Any:
            token.cancel()  # the user presses "Durdur" while the model writes
            return None

    with cancel.using(token), pytest.raises(cancel.Cancelled):
        engine(StoppedClient(SHORTLIST)).analyze("kredi kartı")
