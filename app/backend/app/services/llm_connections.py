"""Saved connections as the model port uses them (data-dictionary 003-llm-connection).

Requirement 5 and Decision 16: an analysis reads the active integration from PostgreSQL once,
right before its model steps, and uses that snapshot to the end. Requirement 20 and Decision 9: an
API key is sealed with AES-256-GCM bound to the tenant, the integration and the address origin;
whatever cannot be opened is ``key_unreadable`` and is never sent without its key.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.logging import log_event
from app.core.secret_cipher import SecretCipher, SecretUnreadable, decode_encryption_key
from app.domain.llm import (
    LlmChatPort,
    LlmConnection,
    LlmOutcome,
    ModelState,
    endpoint_origin,
    probe_message,
)
from app.domain.models.llm_integration import LlmIntegration
from app.infrastructure.llm.openai_adapter import OpenAICompatibleAdapter
from app.infrastructure.repositories.llm_integration_repository import (
    LlmIntegrationRepository,
)

logger = logging.getLogger("app.llm")

# llm_integration.key_unreadable is logged once per process for each connection version.
_reported_unreadable: set[tuple[str, str]] = set()
_reported_lock = threading.Lock()


class KeyStorageUnavailable(Exception):
    """No settings encryption key is configured, so no API key can be stored."""


def key_context(tenant_public_id: str, integration_public_id: str, endpoint: str) -> str:
    return f"llm_integration:{tenant_public_id}:{integration_public_id}:{endpoint_origin(endpoint)}"


class ConnectionKeys:
    """Seals and opens API keys with the settings encryption key of this process."""

    def __init__(self, settings: Settings) -> None:
        key = settings.settings_encryption_key
        self._cipher = (
            SecretCipher(decode_encryption_key(key.get_secret_value())) if key is not None else None
        )

    @property
    def available(self) -> bool:
        return self._cipher is not None

    def seal(self, api_key: str, *, tenant_public_id: str, row: LlmIntegration) -> str:
        if self._cipher is None:
            raise KeyStorageUnavailable()
        return self._cipher.encrypt(
            api_key, context=key_context(tenant_public_id, row.public_id, row.endpoint)
        )

    def open(self, row: LlmIntegration, *, tenant_public_id: str) -> str | None:
        """The row's key, None when it has none; raises SecretUnreadable when it cannot open."""

        if row.api_key_ciphertext is None:
            return None
        if self._cipher is None:
            raise SecretUnreadable()
        try:
            context = key_context(tenant_public_id, row.public_id, row.endpoint)
        except ValueError:
            raise SecretUnreadable() from None
        return self._cipher.decrypt(row.api_key_ciphertext, context=context)

    def connection(
        self, row: LlmIntegration, *, tenant_public_id: str
    ) -> LlmConnection | LlmOutcome:
        """The row as a connection, or ``key_unreadable`` (logged once per row version)."""

        try:
            api_key = self.open(row, tenant_public_id=tenant_public_id)
        except SecretUnreadable:
            report_key_unreadable(row)
            return LlmOutcome.KEY_UNREADABLE
        return connection_of(row, api_key)


def connection_of(row: LlmIntegration, api_key: str | None) -> LlmConnection:
    return LlmConnection(
        endpoint=row.endpoint,
        chat_model=row.chat_model,
        temperature=row.temperature,
        timeout_seconds=row.timeout_seconds,
        reasoning_effort=row.reasoning_effort,
        seed=row.seed,
        api_key=api_key,
        public_id=row.public_id,
    )


def report_key_unreadable(row: LlmIntegration) -> None:
    version = (row.public_id, row.updated_at.isoformat() if row.updated_at else "")
    with _reported_lock:
        if version in _reported_unreadable:
            return
        _reported_unreadable.add(version)
    log_event(logger, "llm_integration.key_unreadable", integration_public_id=row.public_id)


@dataclass(frozen=True, slots=True)
class ActiveConnection:
    """The active row, if any, and what an analysis can use of it."""

    row: LlmIntegration | None
    connection: LlmConnection | LlmOutcome


async def active_connection(
    session: AsyncSession, keys: ConnectionKeys, *, tenant_id: int, tenant_public_id: str
) -> ActiveConnection:
    """Requirement 5: the active connection, ``not_configured`` or ``key_unreadable``."""

    row = await LlmIntegrationRepository(session).active(tenant_id)
    if row is None or not row.chat_model:
        return ActiveConnection(row, LlmOutcome.NOT_CONFIGURED)
    return ActiveConnection(row, keys.connection(row, tenant_public_id=tenant_public_id))


async def model_state(port: LlmChatPort, active: ActiveConnection) -> ModelState:
    """Requirement 12: ``ok``, ``none`` or ``down`` with the class and the check message."""

    connection = active.connection
    if active.row is None or connection is LlmOutcome.NOT_CONFIGURED:
        return ModelState.not_configured()
    if isinstance(connection, LlmOutcome):
        return ModelState(
            state="down",
            model=active.row.chat_model,
            code=connection,
            reason=probe_message(connection),
        )
    return ModelState.from_probe(connection.chat_model, await port.health(connection))


class LlmGateway:
    """The model port as an analysis or the measurement script uses it (Decision 1).

    ``snapshot`` reads the active connection once (Requirement 5); ``port`` then serves every
    chat call and health check of that analysis with it.
    """

    def __init__(
        self,
        *,
        port: LlmChatPort,
        session_factory: async_sessionmaker[AsyncSession],
        keys: Callable[[], ConnectionKeys],
    ) -> None:
        self.port = port
        self._session_factory = session_factory
        self._keys = keys

    async def _active(self, *, tenant_id: int, tenant_public_id: str) -> ActiveConnection:
        async with self._session_factory() as session:
            return await active_connection(
                session, self._keys(), tenant_id=tenant_id, tenant_public_id=tenant_public_id
            )

    async def snapshot(
        self, *, tenant_id: int, tenant_public_id: str
    ) -> LlmConnection | LlmOutcome:
        active = await self._active(tenant_id=tenant_id, tenant_public_id=tenant_public_id)
        return active.connection

    async def model_state(self, *, tenant_id: int, tenant_public_id: str) -> ModelState:
        """The model status object of question-analysis ``GET /status`` (Requirement 12)."""

        active = await self._active(tenant_id=tenant_id, tenant_public_id=tenant_public_id)
        return await model_state(self.port, active)


@lru_cache(maxsize=4)
def _adapter(ca_bundle: str, max_concurrent_calls: int) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(ca_bundle=ca_bundle, max_concurrent_calls=max_concurrent_calls)


def shared_adapter(settings: Settings) -> OpenAICompatibleAdapter:
    """The process's one adapter: one slot limit, one learned-feature and health store."""

    return _adapter(settings.llm_ca_bundle, settings.llm_max_concurrent_calls)


def llm_gateway(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> LlmGateway:
    """The model port of analyses and the measurement script over the shared adapter."""

    return LlmGateway(
        port=shared_adapter(settings),
        session_factory=session_factory,
        keys=lambda: ConnectionKeys(settings),
    )
