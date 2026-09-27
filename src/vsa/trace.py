"""Request tracing for the admin screen: which steps an analysis went through and how long
each took — search arms, analyst steps, every LLM call with its retries and tokens.

Pure: spans are collected in memory. Nothing is recorded unless the caller opened a
``recording()``; without one every function here is a cheap no-op, so the CLI, eval and
the explorer run untraced. The web server writes finished traces (I/O stays there).

Worker threads do not inherit the recording; submit their work through ``carry``.
"""

from __future__ import annotations

import contextvars
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")

STEP, LLM, EMBED, EVENT = "step", "llm", "embed", "event"


@dataclass(slots=True)
class Span:
    id: int
    parent: int | None
    name: str
    kind: str
    start: float  # seconds since the trace began
    end: float | None = None
    detail: str = ""
    status: str = "ok"  # ok | warn | error
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        end = self.start if self.end is None else self.end
        out: dict[str, Any] = {
            "id": self.id,
            "parent": self.parent,
            "name": self.name,
            "kind": self.kind,
            "start_ms": round(self.start * 1000),
            "ms": round((end - self.start) * 1000),
            "status": self.status,
        }
        if self.detail:
            out["detail"] = self.detail
        if self.data:
            out["data"] = self.data
        return out


class Trace:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.spans: list[Span] = []
        self._lock = threading.Lock()

    def now(self) -> float:
        return time.perf_counter() - self.t0

    def open(self, name: str, parent: int | None, kind: str, detail: str = "") -> Span:
        with self._lock:
            span = Span(len(self.spans), parent, name, kind, self.now(), detail=detail)
            self.spans.append(span)
        return span

    def close(self, span: Span) -> None:
        span.end = self.now()

    def to_list(self) -> list[dict[str, Any]]:
        now = self.now()
        with self._lock:
            for s in self.spans:
                if s.end is None:  # left open by an exception
                    s.end, s.status = now, "error"
            return [s.to_dict() for s in self.spans]

    def totals(self) -> dict[str, int]:
        """LLM calls and tokens over the whole trace."""
        calls = [s for s in self.spans if s.kind == LLM]
        return {
            "llm_calls": len(calls),
            "prompt_tokens": sum(int(s.data.get("prompt_tokens", 0)) for s in calls),
            "completion_tokens": sum(int(s.data.get("completion_tokens", 0)) for s in calls),
        }


_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar("vsa_trace", default=None)
_parent: contextvars.ContextVar[int | None] = contextvars.ContextVar("vsa_span", default=None)


@contextmanager
def recording() -> Iterator[Trace]:
    """Collect every span opened inside this block (and in work passed through ``carry``)."""
    trace = Trace()
    t1, t2 = _trace.set(trace), _parent.set(None)
    try:
        yield trace
    finally:
        _parent.reset(t2)
        _trace.reset(t1)


@contextmanager
def span(name: str, detail: str = "", kind: str = STEP) -> Iterator[Span | None]:
    """A timed step; nested spans become its children. An exception marks it as an error."""
    trace = _trace.get()
    if trace is None:
        yield None
        return
    s = trace.open(name, _parent.get(), kind, detail)
    token = _parent.set(s.id)
    try:
        yield s
    except BaseException:
        s.status = "error"
        raise
    finally:
        _parent.reset(token)
        trace.close(s)


def event(name: str, detail: str = "", status: str = "warn") -> None:
    """A moment worth seeing on the timeline: a retry, a fallback, a dropped feature."""
    trace = _trace.get()
    if trace is None:
        return
    s = trace.open(name, _parent.get(), EVENT, detail)
    s.status = status
    trace.close(s)


def current() -> Span | None:
    """The innermost open span of this thread's recording (None when not recording)."""
    trace, sid = _trace.get(), _parent.get()
    return None if trace is None or sid is None else trace.spans[sid]


def count(**values: int) -> None:
    """Add to counters (tokens, requests) of the innermost open span."""
    s = current()
    if s is not None:
        for k, v in values.items():
            s.data[k] = int(s.data.get(k, 0)) + v


class Laps:
    """Consecutive steps without nesting the code: each ``lap(name)`` ends the previous."""

    def __init__(self) -> None:
        self._cm: Any = None
        self._span: Span | None = None

    def __call__(self, name: str, detail: str = "") -> None:
        self.done()
        self._cm = span(name, detail)
        self._span = self._cm.__enter__()

    def note(self, detail: str) -> None:
        """Describe the running lap once its outcome is known."""
        if self._span is not None:
            self._span.detail = detail

    def done(self) -> None:
        if self._cm is not None:
            cm, self._cm, self._span = self._cm, None, None
            cm.__exit__(None, None, None)


def carry(fn: Callable[..., T]) -> Callable[..., T]:
    """``fn`` bound to the caller's recording, for a worker thread (one copy per task)."""
    ctx = contextvars.copy_context()
    return lambda *args: ctx.run(fn, *args)
