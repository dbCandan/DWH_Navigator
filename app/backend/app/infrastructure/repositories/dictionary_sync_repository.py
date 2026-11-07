"""Persistence of the source connection, update runs and their reports (011-dictionary-sync)."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.dictionary_sync import (
    DictionarySource,
    DictionarySyncChange,
    DictionarySyncRun,
    DictionarySyncSuggestion,
)

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
