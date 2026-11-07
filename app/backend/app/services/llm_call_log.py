"""Writes finished chat calls to the LLM call log and drops the rows past the retention period.

A failed write only loses that row: it never reaches the chat call, and the log event carries the
error's class alone, since the error text could quote a body.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log_event
from app.domain.llm_call_log import LlmCallTrace
from app.infrastructure.repositories.llm_call_log_repository import LlmCallLogRepository

logger = logging.getLogger("app.llm")


class LlmCallLogWriter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, days: int) -> None:
        self._session_factory = session_factory
        self._retention = timedelta(days=days)

    async def __call__(self, trace: LlmCallTrace) -> None:
        try:
            async with self._session_factory() as session:
                repository = LlmCallLogRepository(session)
                repository.add(trace)
                await session.flush()
                await repository.prune(datetime.now(UTC) - self._retention)
                await session.commit()
        except Exception as error:  # noqa: BLE001 - the log must never fail a model call
            log_event(logger, "llm_call_log.write_failed", error_class=type(error).__name__)
