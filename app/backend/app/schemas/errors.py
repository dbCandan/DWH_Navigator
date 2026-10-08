"""The single error envelope in the API contract (application-foundation 001 Requirement 15)."""

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


def error_responses(described: dict[int, str]) -> dict[int | str, dict[str, Any]]:
    """OpenAPI responses whose body is the envelope; the text names the stable codes."""

    return {
        status: {"model": ErrorResponse, "description": text} for status, text in described.items()
    }
