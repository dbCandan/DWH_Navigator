"""What the LLM call log keeps of one chat call: its summary and the bodies that went over the wire.

The log is an operator's debugging view, kept in PostgreSQL for a limited time. It holds what the
model was sent and what it answered, so it never reaches the application log or telemetry. The API
key is cut out of every body; the address and the request headers are not kept.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.domain.llm import LlmCallSummary

# A body longer than this is kept cut, with its `*_truncated` flag set.
MAX_BODY_CHARS = 200_000
SECRET_MASK = "***"


def readable_body(raw: bytes, secret: str | None) -> tuple[str, bool]:
    """``raw`` as text a person can read and PostgreSQL can store, and whether it was cut.

    The adapter writes bodies with ASCII escapes, so JSON is written again with its Turkish letters
    as they are. PostgreSQL text cannot hold NUL or a lone surrogate from a JSON escape.
    """

    text = raw.decode("utf-8", "replace")
    try:
        text = json.dumps(json.loads(text), ensure_ascii=False)
    except (ValueError, RecursionError):
        pass
    if secret:
        text = text.replace(secret, SECRET_MASK)
    text = text.replace("\x00", "").encode("utf-8", "replace").decode("utf-8")
    return text[:MAX_BODY_CHARS], len(text) > MAX_BODY_CHARS


@dataclass(slots=True)
class LlmExchange:
    """One HTTP request of a chat call; ``status`` stays empty when no response arrived."""

    request: str
    request_truncated: bool
    status: int | None = None
    response: str = ""
    response_truncated: bool = False
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "request_truncated": self.request_truncated,
            "status": self.status,
            "response": self.response,
            "response_truncated": self.response_truncated,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class LlmCallTrace:
    """A finished chat call as the log stores it."""

    tenant_id: int
    summary: LlmCallSummary
    analysis_public_id: str | None = None
    exchanges: tuple[LlmExchange, ...] = field(default=(), repr=False)


CallLogSink = Callable[[LlmCallTrace], Awaitable[None]]
