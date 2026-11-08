"""Writes finished chat calls to the LLM call log, drops the rows past the retention period and
deletes the rows a manager asks to remove.

A failed write only loses that row: it never reaches the chat call, and the log event carries the
error's class alone, since the error text could quote a body.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log_event
from app.domain.llm_call_log import LlmCallTrace
from app.infrastructure.repositories.llm_call_log_repository import (
    CallLogFilters,
    LlmCallLogRepository,
)

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


async def delete_calls(
    session: AsyncSession,
    tenant_id: int,
    filters: CallLogFilters,
    until: datetime,
    *,
    everything: bool,
    actor_public_id: str,
) -> dict[str, int]:
    """Delete the tenant's matching calls for good, in one transaction, and log who did it.

    ``everything`` ignores ``filters``; ``until`` keeps the calls that arrived after the page
    showed its count. The event carries no filter text, since the search text could quote a body.
    """

    repository = LlmCallLogRepository(session)
    deleted = await repository.delete_matching(
        tenant_id, CallLogFilters() if everything else filters, until
    )
    remaining = await repository.count(tenant_id)
    await session.commit()
    log_event(
        logger,
        "llm_call_log.deleted",
        count=deleted,
        scope="all" if everything else "filter",
        user_public_id=actor_public_id,
    )
    return {"deleted_count": deleted, "remaining_count": remaining}
