"""Stopping an analysis: waits end, open LLM connections are cut, nothing falls back."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest

from vsa import cancel
from vsa.llm.client import LLMError, OpenAICompatibleClient


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


@pytest.fixture
def silent_server() -> Iterator[tuple[str, list[str]]]:
    """A model server that accepts the request and never answers (like a stuck model)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    events: list[str] = []

    def serve() -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            events.append("accepted")
            conn.settimeout(20)
            try:
                while conn.recv(65536):  # read the request, then wait for the client
                    pass
                events.append("client left")
            except OSError:
                events.append("client left")
            finally:
                conn.close()

    threading.Thread(target=serve, daemon=True).start()
    yield f"http://127.0.0.1:{srv.getsockname()[1]}/v1", events
    srv.close()


def test_stop_cuts_a_hanging_llm_call(silent_server: tuple[str, list[str]]) -> None:
    endpoint, events = silent_server
    client = OpenAICompatibleClient(endpoint, "m", timeout=30)
    token = cancel.Token()
    outcome: list[object] = []

    def run() -> None:
        with cancel.using(token):
            try:
                outcome.append(client.chat_json("s", "u", {"type": "object"}))
            except BaseException as exc:  # noqa: BLE001 - the test inspects what came out
                outcome.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.5)
    started = time.perf_counter()
    token.cancel()
    worker.join(5)
    assert not worker.is_alive() and time.perf_counter() - started < 3
    assert isinstance(outcome[0], cancel.Cancelled)  # not None: no fallback to rules
    assert not isinstance(outcome[0], LLMError)
    for _ in range(50):
        if "client left" in events:
            break
        time.sleep(0.05)
    assert events[:2] == ["accepted", "client left"]  # the connection was really closed
