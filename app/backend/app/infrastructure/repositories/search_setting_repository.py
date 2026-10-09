"""Persistence of changed search and answer settings (data-dictionary 009).

Only values that differ from the code's defaults are kept; a value set back to its default
soft-deletes its row (Requirement 4).
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.search_setting import SearchSetting


class SearchSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def stored(self, tenant_id: int) -> dict[str, Any]:
        """The tenant's non-deleted rows as ``key -> value``."""

        rows = await self.session.execute(
            select(SearchSetting.setting_key, SearchSetting.value)
            .where(
                SearchSetting.tenant_id == tenant_id,
                SearchSetting.is_deleted.is_(False),
            )
            .order_by(SearchSetting.setting_key)
        )
        return {str(key): value for key, value in rows.all()}

    async def write(
        self,
        tenant_id: int,
        values: Mapping[str, Any],
        defaults: Mapping[str, Any],
        *,
        user_id: int | None,
        now: datetime,
    ) -> None:
        """Store ``values``: a default value soft-deletes its row, another one is kept."""

        current = {
            row.setting_key: row
            for row in (
                await self.session.execute(
                    select(SearchSetting)
                    .where(
                        SearchSetting.tenant_id == tenant_id,
                        SearchSetting.setting_key.in_(list(values)),
                        SearchSetting.is_deleted.is_(False),
                    )
                    .with_for_update()
                )
            ).scalars()
        }
        for key, value in values.items():
            row = current.get(key)
            if value == defaults[key]:
                if row is not None:
                    await self.session.execute(
                        update(SearchSetting)
                        .where(SearchSetting.search_setting_id == row.search_setting_id)
                        .values(
                            is_deleted=True,
                            deleted_at=now,
                            deleted_by=user_id,
                            updated_at=now,
                            updated_by=user_id,
                        )
                    )
                continue
            if row is not None:
                await self.session.execute(
                    update(SearchSetting)
                    .where(SearchSetting.search_setting_id == row.search_setting_id)
                    .values(value=value, updated_at=now, updated_by=user_id)
                )
                continue
            self.session.add(
                SearchSetting(
                    tenant_id=tenant_id,
                    setting_key=key,
                    value=value,
                    created_at=now,
                    updated_at=now,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
        await self.session.flush()
