"""The model port the analyst uses (question-analysis Requirement 24, llm-connection Decision 1).

The contract is the source's ``LLMClient``: ``available``, ``model``, ``health()`` and
``chat_json(system, user, schema, *, max_tokens)`` returning the parsed JSON object or None.
In place of the source's free-text ``last_error`` a failure is a fixed class of the
llm-connection PRD (its Requirement 13) with the HTTP status when there was one; the
"Analiz yapılamadı" reason is derived from it (question-analysis Requirement 5). The
infrastructure adapter that talks to a model server belongs to the llm-connection PRD; each
analysis uses a view of the port of its own, so a failure never leaks between analyses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class FailureCode(StrEnum):
    """The fixed failure classes of a model call or a server check (llm-connection)."""

    NOT_CONFIGURED = "not_configured"
    KEY_UNREADABLE = "key_unreadable"
    NETWORK_POLICY_DENIED = "network_policy_denied"
    NAME_UNRESOLVED = "name_unresolved"
    CONNECT_REFUSED = "connect_refused"
    CONNECT_ERROR = "connect_error"
    TLS_ERROR = "tls_error"
    TIMEOUT = "timeout"
    UNAUTHORIZED = "unauthorized"
    CONTEXT_EXCEEDED = "context_exceeded"
    UPSTREAM_STATUS = "upstream_status"
    INVALID_RESPONSE = "invalid_response"
    OUTPUT_TRUNCATED = "output_truncated"
    INVALID_JSON = "invalid_json"
    RESPONSE_TOO_LARGE = "response_too_large"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ModelFailure:
    """Why a model call or a server check failed. Never carries the server's text."""

    code: FailureCode
    http_status: int | None = None


@dataclass(frozen=True, slots=True)
class ModelSampling:
    """The chat model and its sampling values: part of the saved-answer fingerprint."""

    model: str
    temperature: float
    reasoning_effort: str
    seed: int


class LLMClient(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def model(self) -> str: ...

    @property
    def last_failure(self) -> ModelFailure | None:
        """Why the last chat call returned None; None when it did not fail."""
        ...

    def health(self) -> ModelFailure | None:
        """None when the chat model's server answers, else why not."""
        ...

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None: ...


class NullClient:
    """No model configured: there is no analyst, so no answer (ADR-038)."""

    available = False
    model = ""
    last_failure: ModelFailure | None = None

    def health(self) -> ModelFailure | None:
        return ModelFailure(FailureCode.NOT_CONFIGURED)

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        return None
