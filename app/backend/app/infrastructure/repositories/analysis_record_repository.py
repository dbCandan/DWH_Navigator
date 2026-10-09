"""Persistence of analysis records (data-dictionary 008-analysis-records).

question-analysis opens, starts and finishes a record through this repository; a record in a
terminal state is never updated again (every update is guarded by the running states). The
administration queries read and delete only terminal records (Requirement 5). Every query is scoped
to a tenant; the text filter is a bound parameter with ``%``, ``_`` and ``\\`` escaped.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.analysis_records import TERMINAL_STATES, JobState
from app.domain.models.analysis_record import AnalysisRecord
from app.domain.models.user import User

_RUNNING = (JobState.QUEUED.value, JobState.RUNNING.value)
_TERMINAL = tuple(sorted(state.value for state in TERMINAL_STATES))


@dataclass(frozen=True, slots=True)
class RecordFilter:
    """Which terminal records an administration request means (Requirement 6 and 11)."""

    until: datetime
    asked_from: datetime | None = None
    flow: str | None = None
    asker_public_id: str | None = None
    folded_text: str | None = None


@dataclass(frozen=True, slots=True)
class RecordRow:
    record: AnalysisRecord
    asker_public_id: str
    asker_display_name: str


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class AnalysisRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- question-analysis: the job's own record -------------------------------------------------

    async def add(self, record: AnalysisRecord) -> None:
        self.session.add(record)
        await self.session.flush()

    async def update_unfinished(
        self, tenant_id: int, public_id: str, values: dict[str, Any], *, from_queued: bool = False
    ) -> bool:
        """Update a record still queued (or running); False when it is terminal or gone."""

        states = (JobState.QUEUED.value,) if from_queued else _RUNNING
        result = await self.session.execute(
            update(AnalysisRecord)
            .where(
                AnalysisRecord.tenant_id == tenant_id,
                AnalysisRecord.public_id == public_id,
                AnalysisRecord.state.in_(states),
            )
            .values(**values, updated_at=func.now())
            .returning(AnalysisRecord.analysis_record_id)
        )
        return result.first() is not None

    async def interrupt_unfinished(self, accepted_before: datetime, values: dict[str, Any]) -> int:
        """Every record of any tenant still queued or running from before this process."""

        result = await self.session.execute(
            update(AnalysisRecord)
            .where(
                AnalysisRecord.state.in_(_RUNNING),
                AnalysisRecord.asked_at < accepted_before,
            )
            .values(**values, updated_at=func.now())
            .returning(AnalysisRecord.analysis_record_id)
        )
        return len(result.all())

    async def owned_by(self, tenant_id: int, public_id: str) -> RecordRow | None:
        """A record in any state with its asker (question-analysis checks the owner)."""

        row = (
            await self.session.execute(
                select(AnalysisRecord, User.public_id, User.display_name)
                .join(User, User.user_id == AnalysisRecord.asked_by)
                .where(AnalysisRecord.tenant_id == tenant_id, AnalysisRecord.public_id == public_id)
            )
        ).first()
        return None if row is None else RecordRow(row[0], str(row[1]), str(row[2]))

    # --- administration: terminal records only ---------------------------------------------------

    def _conditions(self, tenant_id: int, f: RecordFilter) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [
            AnalysisRecord.tenant_id == tenant_id,
            AnalysisRecord.state.in_(_TERMINAL),
            AnalysisRecord.asked_at <= f.until,
        ]
        if f.asked_from is not None:
            conditions.append(AnalysisRecord.asked_at >= f.asked_from)
        if f.flow is not None:
            conditions.append(AnalysisRecord.flow == f.flow)
        if f.asker_public_id is not None:
            conditions.append(
                AnalysisRecord.asked_by.in_(
                    select(User.user_id).where(User.public_id == f.asker_public_id)
                )
            )
        if f.folded_text:
            pattern = f"%{escape_like(f.folded_text)}%"
            conditions.append(AnalysisRecord.search_key.like(pattern, escape="\\"))
        return conditions

    def _rows(self) -> Any:
        return select(AnalysisRecord, User.public_id, User.display_name).join(
            User, User.user_id == AnalysisRecord.asked_by
        )

    async def page(
        self, tenant_id: int, f: RecordFilter, *, offset: int, limit: int
    ) -> tuple[list[RecordRow], int]:
        conditions = self._conditions(tenant_id, f)
        total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(AnalysisRecord).where(and_(*conditions))
                )
            ).scalar_one()
        )
        rows = await self.session.execute(
            self._rows()
            .where(*conditions)
            .order_by(AnalysisRecord.asked_at.desc(), AnalysisRecord.analysis_record_id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [RecordRow(r[0], str(r[1]), str(r[2])) for r in rows.all()], total

    async def figures(self, tenant_id: int, f: RecordFilter) -> list[dict[str, Any]]:
        """The numbers of every matching record the summary is computed from; no texts."""

        columns = (
            AnalysisRecord.flow,
            AnalysisRecord.verdict,
            AnalysisRecord.asked_at,
            AnalysisRecord.duration_ms,
            AnalysisRecord.llm_calls,
            AnalysisRecord.prompt_tokens,
            AnalysisRecord.completion_tokens,
            AnalysisRecord.phase_queue_ms,
            AnalysisRecord.phase_saved_answer_lookup_ms,
            AnalysisRecord.phase_model_check_ms,
            AnalysisRecord.phase_rule_hints_ms,
            AnalysisRecord.phase_analyst_pick_ms,
            AnalysisRecord.phase_analyst_write_ms,
            User.public_id.label("asker_public_id"),
            User.display_name.label("asker_display_name"),
        )
        rows = await self.session.execute(
            select(*columns)
            .join(User, User.user_id == AnalysisRecord.asked_by)
            .where(*self._conditions(tenant_id, f))
            .order_by(AnalysisRecord.asked_at.desc(), AnalysisRecord.analysis_record_id.desc())
        )
        return [dict(row._mapping) for row in rows.all()]

    async def verdicts_since(
        self, tenant_id: int, since: datetime
    ) -> Sequence[tuple[datetime, str | None]]:
        rows = await self.session.execute(
            select(AnalysisRecord.asked_at, AnalysisRecord.verdict).where(
                AnalysisRecord.tenant_id == tenant_id,
                AnalysisRecord.state.in_(_TERMINAL),
                AnalysisRecord.asked_at >= since,
            )
        )
        return [(r[0], r[1]) for r in rows.all()]

    async def askers(self, tenant_id: int) -> list[tuple[str, str]]:
        rows = await self.session.execute(
            select(User.public_id, User.display_name)
            .where(
                User.user_id.in_(
                    select(AnalysisRecord.asked_by).where(
                        AnalysisRecord.tenant_id == tenant_id,
                        AnalysisRecord.state.in_(_TERMINAL),
                    )
                )
            )
            .order_by(User.display_name, User.public_id)
        )
        return [(str(r[0]), str(r[1])) for r in rows.all()]

    async def terminal(self, tenant_id: int, public_id: str) -> RecordRow | None:
        row = (
            await self.session.execute(
                self._rows().where(
                    AnalysisRecord.tenant_id == tenant_id,
                    AnalysisRecord.public_id == public_id,
                    AnalysisRecord.state.in_(_TERMINAL),
                )
            )
        ).first()
        return None if row is None else RecordRow(row[0], str(row[1]), str(row[2]))

    async def delete_matching(self, tenant_id: int, f: RecordFilter) -> int:
        result = await self.session.execute(
            delete(AnalysisRecord)
            .where(*self._conditions(tenant_id, f))
            .returning(AnalysisRecord.analysis_record_id)
        )
        return len(result.all())

    async def count_terminal(self, tenant_id: int) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(AnalysisRecord)
                    .where(
                        AnalysisRecord.tenant_id == tenant_id,
                        AnalysisRecord.state.in_(_TERMINAL),
                    )
                )
            ).scalar_one()
        )
