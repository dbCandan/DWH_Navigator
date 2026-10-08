"""Requests and responses of the AI page's endpoints (data-dictionary 003-llm-connection).

Unknown fields are refused (422 ``invalid_request``). Numeric fields accept a number or a numeric
text, as the source form did; a value that is not a number is a Requirement 2 error. No response
carries an API key or its ciphertext: only ``has_key``.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)

NumberInput = StrictInt | StrictFloat | StrictStr
LlmFailureCode = Literal[
    "not_configured",
    "key_unreadable",
    "network_policy_denied",
    "name_unresolved",
    "connect_refused",
    "connect_error",
    "tls_error",
    "timeout",
    "unauthorized",
    "context_exceeded",
    "upstream_status",
    "invalid_response",
    "invalid_json",
    "response_too_large",
    "cancelled",
]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmIntegrationCreate(_Request):
    """A new integration: name and address; every other field takes its default."""

    name: StrictStr
    endpoint: StrictStr
    api_key: StrictStr | None = None
    chat_model: StrictStr | None = None
    temperature: NumberInput | None = None
    timeout_seconds: NumberInput | None = None
    reasoning_effort: StrictStr | None = None
    seed: NumberInput | None = None
    # Absent: the integration is saved inactive.
    activate: StrictBool | None = None
    # True turns the currently active integration off in the same transaction.
    replace: StrictBool = False


class LlmIntegrationUpdate(_Request):
    """A partial update: an absent field keeps its value; ``api_key`` ``""`` deletes the key."""

    name: StrictStr | None = None
    endpoint: StrictStr | None = None
    api_key: StrictStr | None = None
    chat_model: StrictStr | None = None
    temperature: NumberInput | None = None
    timeout_seconds: NumberInput | None = None
    reasoning_effort: StrictStr | None = None
    seed: NumberInput | None = None
    activate: StrictBool | None = None
    replace: StrictBool = False


class LlmActiveChange(_Request):
    active: StrictBool
    replace: StrictBool = False


class LlmModelsRequest(_Request):
    """A saved integration, form values, or both; a form key replaces the saved one."""

    public_id: UUID | None = None
    endpoint: StrictStr | None = None
    api_key: StrictStr | None = None


class LlmTestRequest(_Request):
    """Form values over a saved integration; ``record`` only with ``public_id`` alone."""

    public_id: UUID | None = None
    # Accepted from the form and ignored.
    name: StrictStr | None = None
    endpoint: StrictStr | None = None
    api_key: StrictStr | None = None
    chat_model: StrictStr | None = None
    temperature: NumberInput | None = None
    timeout_seconds: NumberInput | None = None
    reasoning_effort: StrictStr | None = None
    seed: NumberInput | None = None
    record: StrictBool = False


class LlmLastTest(BaseModel):
    at: datetime
    ok: bool
    summary: str


class LlmIntegrationItem(BaseModel):
    public_id: UUID
    name: str
    endpoint: str
    has_key: bool
    active: bool
    chat_model: str
    temperature: float
    timeout_seconds: int
    reasoning_effort: str
    seed: int
    last_test: LlmLastTest | None
    created_at: datetime
    updated_at: datetime


class LlmActiveIntegration(BaseModel):
    public_id: UUID
    name: str
    model: str


class LlmModelState(BaseModel):
    """Requirement 12; ``name`` is the active integration's name on the AI page."""

    state: Literal["ok", "none", "down"]
    model: str
    code: LlmFailureCode | None
    reason: str
    name: str | None


class LlmIntegrationsState(BaseModel):
    items: list[LlmIntegrationItem]
    total: int
    active: LlmActiveIntegration | None
    model_state: LlmModelState
    environment: Literal["local", "nonprod"]
    accepts_http: bool
    # False when no settings encryption key is configured: an API key cannot be saved.
    key_storage: bool


class LlmIntegrationCreated(LlmIntegrationsState):
    item: LlmIntegrationItem


class LlmIntegrationUpdated(LlmIntegrationsState):
    item: LlmIntegrationItem
    # True when the address origin changed without a new key and the saved key was deleted.
    key_cleared: bool


class LlmModelRow(BaseModel):
    id: str
    type: str
    loaded: bool | None
    context: int | None
    owner: str
    quant: str
    # Whether this is the active integration's chat model.
    in_use: bool


class LlmModelsResult(BaseModel):
    ok: bool
    code: LlmFailureCode | None
    message: str
    models: list[LlmModelRow]
    ms: int


class LlmInventoryServer(BaseModel):
    public_id: UUID
    name: str
    active: bool
    ok: bool
    code: LlmFailureCode | None
    message: str
    models: list[LlmModelRow]


class LlmInventory(BaseModel):
    servers: list[LlmInventoryServer]


class LlmTestStep(BaseModel):
    name: str
    ok: bool
    code: LlmFailureCode | None
    detail: str
    ms: int


class LlmTestResult(BaseModel):
    ok: bool
    steps: list[LlmTestStep]
