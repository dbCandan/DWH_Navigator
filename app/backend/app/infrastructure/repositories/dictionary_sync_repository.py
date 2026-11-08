"""Persistence of the source connection, update runs and their reports (011-dictionary-sync)."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.dictionary_sync import (
    DictionarySource,
    DictionarySyncChange,
    DictionarySyncRun,
    DictionarySyncSuggestion,
    DictionaryTrailDigest,
)
from app.domain.models.llm_call_log import LlmCallLog

RUNNING = "running"
INSERT_BATCH = 2000


class DictionarySyncRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def source(self, tenant_id: int) -> DictionarySource | None:
        rows = await self.session.execute(
            select(DictionarySource).where(DictionarySource.tenant_id == tenant_id)
        )
        return rows.scalar_one_or_none()

    async def run(self, tenant_id: int, public_id: str) -> DictionarySyncRun | None:
        rows = await self.session.execute(
            select(DictionarySyncRun).where(
                DictionarySyncRun.tenant_id == tenant_id,
                DictionarySyncRun.public_id == public_id,
            )
        )
        return rows.scalar_one_or_none()

    async def run_by_id(self, run_id: int) -> DictionarySyncRun:
        rows = await self.session.execute(
            select(DictionarySyncRun).where(DictionarySyncRun.dictionary_sync_run_id == run_id)
        )
        return rows.scalar_one()

    async def runs(
        self, tenant_id: int, page: int, page_size: int
    ) -> tuple[list[DictionarySyncRun], int]:
        condition = DictionarySyncRun.tenant_id == tenant_id
        total = await self.session.scalar(
            select(func.count()).select_from(DictionarySyncRun).where(condition)
        )
        rows = await self.session.execute(
            select(DictionarySyncRun)
            .where(condition)
            .order_by(DictionarySyncRun.dictionary_sync_run_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars()), int(total or 0)

    async def is_running(self, tenant_id: int) -> bool:
        """Whether an update or a rollback is running for the tenant."""

        rows = await self.session.execute(
            select(DictionarySyncRun.dictionary_sync_run_id).where(
                DictionarySyncRun.tenant_id == tenant_id,
                DictionarySyncRun.status == "running",
            )
        )
        return rows.first() is not None

    async def pending_runs(self, tenant_id: int) -> list[DictionarySyncRun]:
        rows = await self.session.execute(
            select(DictionarySyncRun).where(
                DictionarySyncRun.tenant_id == tenant_id,
                DictionarySyncRun.status == "pending_approval",
            )
        )
        return list(rows.scalars())

    async def runs_of_versions(self, version_ids: Sequence[int]) -> dict[int, str]:
        if not version_ids:
            return {}
        rows = await self.session.execute(
            select(DictionarySyncRun.dictionary_version_id, DictionarySyncRun.public_id).where(
                DictionarySyncRun.dictionary_version_id.in_(version_ids)
            )
        )
        return {int(version_id): str(public_id) for version_id, public_id in rows.all()}

    async def interrupt_running(self, values: dict[str, Any]) -> int:
        result = await self.session.execute(
            update(DictionarySyncRun).where(DictionarySyncRun.status == RUNNING).values(**values)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def add_changes(self, run_id: int, changes: Sequence[Any]) -> None:
        rows = [
            {
                "dictionary_sync_run_id": run_id,
                "position": position,
                "kind": change.kind,
                "table_key": change.table_key,
                "column_name": change.column_name,
                "field": change.field,
                "old_value": change.old_value,
                "new_value": change.new_value,
                "origin": change.origin,
            }
            for position, change in enumerate(changes)
        ]
        for start in range(0, len(rows), INSERT_BATCH):
            await self.session.execute(
                insert(DictionarySyncChange), rows[start : start + INSERT_BATCH]
            )

    async def changes(
        self, run_id: int, kind: str, search: str, page: int, page_size: int
    ) -> tuple[list[DictionarySyncChange], int]:
        model = DictionarySyncChange
        conditions = [model.dictionary_sync_run_id == run_id]
        if kind:
            conditions.append(model.kind == kind)
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    model.table_key.ilike(pattern, escape="\\"),
                    model.column_name.ilike(pattern, escape="\\"),
                )
            )
        total = await self.session.scalar(
            select(func.count()).select_from(model).where(*conditions)
        )
        rows = await self.session.execute(
            select(model)
            .where(*conditions)
            .order_by(model.position)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars()), int(total or 0)

    async def add_suggestions(self, run_id: int, suggestions: Sequence[Any]) -> None:
        for suggestion in suggestions:
            self.session.add(
                DictionarySyncSuggestion(
                    dictionary_sync_run_id=run_id,
                    kind=suggestion.kind,
                    value=suggestion.value,
                    equivalents=list(suggestion.equivalents),
                    note=suggestion.note,
                )
            )

    async def suggestions(self, run_id: int) -> list[DictionarySyncSuggestion]:
        rows = await self.session.execute(
            select(DictionarySyncSuggestion)
            .where(DictionarySyncSuggestion.dictionary_sync_run_id == run_id)
            .order_by(DictionarySyncSuggestion.dictionary_sync_suggestion_id)
        )
        return list(rows.scalars())

    async def trail_digests(self, tenant_id: int) -> dict[tuple[str, str], str]:
        rows = await self.session.execute(
            select(
                DictionaryTrailDigest.table_key,
                DictionaryTrailDigest.column_name,
                DictionaryTrailDigest.digest,
            ).where(DictionaryTrailDigest.tenant_id == tenant_id)
        )
        return {(table, column): digest for table, column, digest in rows}

    async def save_trail_digests(
        self, tenant_id: int, digests: Mapping[tuple[str, str], str], now: datetime
    ) -> None:
        """Upsert the given digests; rows of columns that left the dictionary go."""

        items = [
            {"tenant_id": tenant_id, "table_key": t, "column_name": c, "digest": d, "updated_at": now}
            for (t, c), d in digests.items()
        ]
        for start in range(0, len(items), INSERT_BATCH):
            batch = items[start : start + INSERT_BATCH]
            statement = pg_insert(DictionaryTrailDigest).values(batch)
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=["tenant_id", "table_key", "column_name"],
                    set_={"digest": statement.excluded.digest, "updated_at": now},
                )
            )

    async def drop_trail_digests(
        self, tenant_id: int, keep: Sequence[tuple[str, str]]
    ) -> None:
        """Rows of columns no longer in the dictionary go."""

        kept = set(keep)
        stored = await self.trail_digests(tenant_id)
        gone = [key for key in stored if key not in kept]
        for start in range(0, len(gone), INSERT_BATCH):
            for table, column in gone[start : start + INSERT_BATCH]:
                await self.session.execute(
                    delete(DictionaryTrailDigest).where(
                        DictionaryTrailDigest.tenant_id == tenant_id,
                        DictionaryTrailDigest.table_key == table,
                        DictionaryTrailDigest.column_name == column,
                    )
                )

    async def append_change(self, run_id: int, change: Any) -> None:
        """One more report line after the run, such as an admin's edit."""

        last = await self.session.scalar(
            select(func.max(DictionarySyncChange.position)).where(
                DictionarySyncChange.dictionary_sync_run_id == run_id
            )
        )
        await self.session.execute(
            insert(DictionarySyncChange).values(
                dictionary_sync_run_id=run_id,
                position=(last + 1) if last is not None else 0,
                kind=change.kind,
                table_key=change.table_key,
                column_name=change.column_name,
                field=change.field,
                old_value=change.old_value,
                new_value=change.new_value,
                origin=change.origin,
            )
        )

    async def average_call_ms(self, tenant_id: int, sample: int = 200) -> float | None:
        """The average duration of recent successful dictionary calls; analysis calls before any."""

        for purpose in ("dictionary_sync", "analysis"):
            recent = (
                select(LlmCallLog.duration_ms)
                .where(
                    LlmCallLog.tenant_id == tenant_id,
                    LlmCallLog.purpose == purpose,
                    LlmCallLog.outcome == "ok",
                )
                .order_by(LlmCallLog.started_at.desc())
                .limit(sample)
                .subquery()
            )
            value = await self.session.scalar(select(func.avg(recent.c.duration_ms)))
            if value:
                return float(value)
        return None
