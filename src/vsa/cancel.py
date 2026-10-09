"""Stopping a running analysis: the web server hands each question a ``Token``; the
"Durdur" button cancels it. Everything the question started stops with it — every open
LLM connection is cut (which also stops generation on the model server), and
``Cancelled`` unwinds the pipeline.

Pure apart from closing the connections registered with it. Without a token (CLI, eval)
every function is a no-op. Worker threads inherit the token through ``trace.carry``
(it copies the whole context).
"""

from __future__ import annotations

import contextlib
import contextvars
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class Cancelled(Exception):  # noqa: N818 - reads as the state, like asyncio.CancelledError
    """The user stopped the analysis. Deliberately not an ``LLMError``: nothing may
    treat it as a model failure and carry on with a fallback."""


class Token:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._hooks: dict[int, Callable[[], None]] = {}
        self._next = 0

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            hooks = list(self._hooks.values())
            self._hooks.clear()
        for hook in hooks:  # outside the lock: a hook may block briefly (socket close)
            with contextlib.suppress(OSError):
                hook()

    def on_cancel(self, hook: Callable[[], None]) -> Callable[[], None]:
        """Run ``hook`` when cancelled (at once if already); returns an unregister call."""
        with self._lock:
            if not self._event.is_set():
                key, self._next = self._next, self._next + 1
                self._hooks[key] = hook
                return lambda: self._hooks.pop(key, None) and None
        hook()
        return lambda: None

    def wait(self, seconds: float) -> bool:
        """Sleep up to ``seconds``; True (early) when cancelled."""
        return self._event.wait(seconds)


_token: contextvars.ContextVar[Token | None] = contextvars.ContextVar("vsa_cancel", default=None)


@contextmanager
def using(token: Token) -> Iterator[Token]:
    reset = _token.set(token)
    try:
        yield token
    finally:
        _token.reset(reset)


def current() -> Token | None:
    return _token.get()


def check() -> None:
    """Raise ``Cancelled`` if this analysis was stopped."""
    t = _token.get()
    if t is not None and t.cancelled:
        raise Cancelled

