"""Responses of the LLM call log endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class LlmCallLogRow(BaseModel):
    """One chat call in the list, without its bodies."""

    public_id: str
    purpose: str
    outcome: str
    model: str
    integration_public_id: str | None
    analysis_public_id: str | None
    started_at: datetime
    wait_ms: int
    duration_ms: int
    http_status: int | None
    requests: int
    repaired: bool
    prompt_tokens: int
    completion_tokens: int


class LlmCallLogsDeleted(BaseModel):
    """How many calls a delete removed and how many of the tenant's calls are left."""

    deleted_count: int
    remaining_count: int


class LlmCallLogPage(BaseModel):
    rows: list[LlmCallLogRow]
    total: int
    retention_days: int
    until: datetime = Field(
        description="When the server read the list; a delete with this until spares later calls."
    )


class LlmCallExchange(BaseModel):
    """One HTTP request of a call; ``status`` is empty when no response arrived."""

    request: str
    request_truncated: bool
    status: int | None
    response: str
    response_truncated: bool
    duration_ms: int


class LlmCallLogDetail(LlmCallLogRow):
    adaptations: list[str]
    exchanges: list[LlmCallExchange]
