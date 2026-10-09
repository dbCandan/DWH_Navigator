"""The Arama ve cevap and Bakım settings and the search index endpoints (search-settings).

data-dictionary/PRDs/009-search-settings Requirement 2-6, 14, 15 and 26. Every request re-reads the
acting account and requires ``yonetici``. A save checks every submitted value first and writes
nothing when one is refused (Requirement 3). In the change queue the new effective values are
compared with the database's: no changed value means no build and no write (``changed: []``);
otherwise the engine is built with them (the word index is recomputed only when one of the six
``indeks`` fields changed) and only then are the values stored, a value equal to its default
soft-deleting its row (Requirement 4 and 6).
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.domain.accounts import ROLE_MANAGER
from app.domain.models.user import User
from app.infrastructure.repositories.search_setting_repository import (
    SearchSettingRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.search.settings import (
    SearchIndexRebuilt,
    SearchIndexState,
    SearchSettings,
    SearchSettingSection,
    SearchSettingsSaved,
)
from app.services.request_scope import acting_user_with_role, active_tenant, forbidden
from app.services.search_index import (
    ChangePlan,
    IndexTrigger,
    SearchChangeBusy,
    SearchIndex,
    SearchIndexBuildFailed,
    ServingEngine,
    search_change_busy,
    search_index_build_failed,
)
from app.services.search_inputs import SearchInputs, checked_settings
from app.services.search_settings_schema import (
    SearchSettingsRejected,
    SettingEffect,
    changed_keys,
    check_values,
    defaults,
    needs_reindex,
    section_dicts,
    settings_digest,
)
from app.services.search_status import index_state

logger = logging.getLogger("app.search")


@dataclass(slots=True)
class _SaveResult:
    changed: list[str] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)


class SearchSettingsService:
    def __init__(self, session: AsyncSession, index: SearchIndex) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.settings = SearchSettingRepository(session)
        self.index = index

    async def _manager(self, context: RequestContext) -> tuple[User, int]:
        actor = await acting_user_with_role(self.users, context, ROLE_MANAGER)
        tenant = await active_tenant(self.users, context)
        return actor, tenant.tenant_id

    async def read(self, context: RequestContext) -> SearchSettings:
        """Requirement 2: the schema, the effective values and the defaults."""

        _actor, tenant_id = await self._manager(context)
        values = checked_settings(await self.settings.stored(tenant_id))
        return SearchSettings(
            sections=[SearchSettingSection.model_validate(s) for s in section_dicts()],
            values=values,
            defaults=defaults(),
        )

    async def save(self, context: RequestContext, submitted: dict[str, Any]) -> SearchSettingsSaved:
        actor, tenant_id = await self._manager(context)
        started = perf_counter()
        try:
            checked = check_values(submitted)
        except SearchSettingsRejected as rejected:
            raise ApplicationError(
                status.HTTP_422_UNPROCESSABLE_CONTENT, rejected.code, rejected.message
            ) from None
        if not checked:
            return SearchSettingsSaved(
                changed=[],
                values=checked_settings(await self.settings.stored(tenant_id)),
                elapsed_ms=round((perf_counter() - started) * 1000),
                index=await index_state(self.index),
            )
        if tenant_id != await self.index.tenant_id():
            raise forbidden()
        result = _SaveResult()
        now = datetime.now(UTC)

        async def plan(inputs: SearchInputs, _serving: ServingEngine | None) -> ChangePlan:
            before = inputs.settings_values
            after = {**before, **checked}
            result.values = after
            result.changed = changed_keys(before, after)
            if not result.changed:
                return ChangePlan(result=result)
            new_inputs = inputs.replace(
                settings_values=after, settings_identity=settings_digest(after)
            )

            async def write(session: AsyncSession) -> None:
                await SearchSettingRepository(session).write(
                    tenant_id,
                    {key: after[key] for key in result.changed},
                    defaults(),
                    user_id=actor.user_id,
                    now=now,
                )

            return ChangePlan(inputs=new_inputs, write=write, result=result)

        try:
            await self.index.change(IndexTrigger.SETTINGS, plan)
        except SearchChangeBusy:
            raise search_change_busy() from None
        except SearchIndexBuildFailed:
            raise search_index_build_failed() from None
        if result.changed:
            effect = (
                SettingEffect.REINDEX
                if needs_reindex(result.changed)
                else (SettingEffect.IMMEDIATE)
            )
            log_event(
                logger,
                "search_settings.changed",
                keys=",".join(result.changed),
                effect=effect.value,
                user_public_id=actor.public_id,
            )
        return SearchSettingsSaved(
            changed=result.changed,
            values=result.values,
            elapsed_ms=round((perf_counter() - started) * 1000),
            index=await index_state(self.index),
        )

    async def index_state(self, context: RequestContext) -> SearchIndexState:
        await self._manager(context)
        return await index_state(self.index)

    async def rebuild(self, context: RequestContext) -> SearchIndexRebuilt:
        """Requirement 14: rebuild from the current inputs even when nothing changed."""

        await self._manager(context)
        started = perf_counter()
        try:
            await self.index.rebuild()
        except SearchChangeBusy:
            raise search_change_busy() from None
        except SearchIndexBuildFailed:
            raise search_index_build_failed() from None
        state = await index_state(self.index)
        return SearchIndexRebuilt(
            **state.model_dump(), elapsed_ms=round((perf_counter() - started) * 1000)
        )
