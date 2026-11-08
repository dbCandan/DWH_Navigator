"""Persistence of the LLM call log; every read is limited to one tenant."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Text, cast, delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from sqlalchemy.sql.elements import ColumnElement

from app.domain.llm_call_log import LlmCallTrace
from app.domain.models.llm_call_log import LlmCallLog


@dataclass(frozen=True, slots=True)
class CallLogFilters:
    purpose: str | None = None
    outcome: str | None = None
    q: str | None = None
    analysis: str | None = None


def _conditions(tenant_id: int, filters: CallLogFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [LlmCallLog.tenant_id == tenant_id]
    if filters.purpose:
        conditions.append(LlmCallLog.purpose == filters.purpose)
    if filters.outcome:
        conditions.append(LlmCallLog.outcome == filters.outcome)
    if filters.analysis:
        conditions.append(LlmCallLog.analysis_public_id == filters.analysis)
    if filters.q:
        needle = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(cast(LlmCallLog.exchanges, Text).ilike(f"%{needle}%", escape="\\"))
    return conditions


class LlmCallLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, trace: LlmCallTrace) -> None:
        summary = trace.summary
        self.session.add(
            LlmCallLog(
                tenant_id=trace.tenant_id,
                purpose=summary.purpose.value,
                outcome=summary.outcome.value,
                model=summary.model,
                integration_public_id=summary.integration_public_id,
                analysis_public_id=trace.analysis_public_id,
                started_at=summary.started_at,
                wait_ms=summary.wait_ms,
                duration_ms=summary.duration_ms,
                http_status=summary.http_status,
                requests=summary.requests,
                repaired=summary.repaired,
                prompt_tokens=summary.prompt_tokens,
                completion_tokens=summary.completion_tokens,
                adaptations=[feature.value for feature in summary.adaptations],
                exchanges=[exchange.as_dict() for exchange in trace.exchanges],
            )
        )

    async def prune(self, before: datetime) -> int:
        result = await self.session.execute(delete(LlmCallLog).where(LlmCallLog.started_at < before))
        return int(result.rowcount) if isinstance(result, CursorResult) else 0

    async def page(
        self, tenant_id: int, filters: CallLogFilters, limit: int
    ) -> tuple[list[LlmCallLog], int]:
        """The newest ``limit`` rows without their bodies, and how many match the filters."""

        conditions = _conditions(tenant_id, filters)
        total = await self.session.scalar(
            select(func.count()).select_from(LlmCallLog).where(*conditions)
        )
        rows = await self.session.scalars(
            select(LlmCallLog)
            .options(defer(LlmCallLog.exchanges))
            .where(*conditions)
            .order_by(LlmCallLog.started_at.desc(), LlmCallLog.llm_call_log_id.desc())
            .limit(limit)
        )
        return list(rows), int(total or 0)

    async def get(self, tenant_id: int, public_id: str) -> LlmCallLog | None:
        result = await self.session.scalar(
            select(LlmCallLog).where(
                LlmCallLog.tenant_id == tenant_id, LlmCallLog.public_id == public_id
            )
        )
        return result
