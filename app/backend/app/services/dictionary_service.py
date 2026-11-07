"""The admin screen's dictionary: state, tables and export (001).

data-dictionary/PRDs/001-dictionary-management Requirement 10-12, 14, 17, 18. Every request re-reads
the acting account and requires ``yonetici`` (the super admin passes); the router checks the same
role. A new version is written by ``write_dictionary_version`` under the PostgreSQL import lock,
taken without waiting (409 ``dictionary_import_in_progress``). No dictionary content or warning
reaches a log line, metric or span.
"""

import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import telemetry
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.domain.accounts import ROLE_MANAGER
from app.domain.dictionary import (
    DICTIONARY_EMPTY_MESSAGE,
    IMPORT_IN_PROGRESS_MESSAGE,
    DictionaryStatus,
    ImportChannel,
)
from app.domain.models.dictionary import DictionaryVersion
from app.domain.models.user import User
from app.infrastructure.repositories.dictionary_repository import (
    DictionaryRepository,
    NewDictionaryVersion,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.dictionary.management import (
    ActiveDictionaryVersion,
    DictionaryImporter,
    DictionaryState,
    DictionaryTable,
    DictionaryTableRecords,
    DictionaryTablesPage,
    DictionaryVersionSummary,
)
from app.services.analysis.dictionary_workbook import export
from app.services.analysis.loader import object_profiles
from app.services.request_scope import acting_user_with_role, active_tenant
from app.services.search_index import SearchIndex

logger = logging.getLogger("app.dictionary")

ISTANBUL = ZoneInfo("Europe/Istanbul")


def dictionary_not_imported() -> ApplicationError:
    return ApplicationError(
        status.HTTP_404_NOT_FOUND, "dictionary_not_imported", DICTIONARY_EMPTY_MESSAGE
    )


def _import_in_progress() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "dictionary_import_in_progress",
        IMPORT_IN_PROGRESS_MESSAGE,
    )


def export_filename(now: datetime) -> str:
    return f"VeriSozlugu_{now.astimezone(ISTANBUL):%Y%m%d_%H%M}.xlsx"


def _summary(
    version: DictionaryVersion, importers: dict[int, tuple[str, str]]
) -> DictionaryVersionSummary:
    importer = importers.get(version.created_by) if version.created_by is not None else None
    return DictionaryVersionSummary(
        public_id=version.public_id,
        version=version.version,
        source_name=version.source_name,
        imported_at=version.imported_at,
        imported_by=(
            DictionaryImporter(public_id=importer[0], display_name=importer[1])
            if importer
            else None
        ),
        channel=ImportChannel(version.channel).value,
        object_count=version.object_count,
        column_count=version.column_count,
        row_count=version.row_count,
        warning_count=version.warning_count,
    )


async def write_dictionary_version(
    session: AsyncSession,
    tenant_id: int,
    version: NewDictionaryVersion,
    *,
    user_id: int | None,
    now: datetime,
) -> DictionaryVersion:
    """Write a version under the import lock (Requirement 8 and 14)."""

    repository = DictionaryRepository(session)
    if not await repository.try_import_lock():
        raise _import_in_progress()
    written, pruned = await repository.write_version(tenant_id, version, user_id=user_id, now=now)
    if pruned is not None:
        log_event(
            logger,
            "dictionary.pruned",
            version=pruned.version,
            objects=pruned.objects,
            columns=pruned.columns,
        )
    return written


class DictionaryService:
    def __init__(self, session: AsyncSession, index: SearchIndex) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.dictionary = DictionaryRepository(session)
        self.index = index

    async def _manager(self, context: RequestContext) -> tuple[User, int]:
        actor = await acting_user_with_role(self.users, context, ROLE_MANAGER)
        tenant = await active_tenant(self.users, context)
        return actor, tenant.tenant_id

    async def _active(self, tenant_id: int) -> DictionaryVersion:
        active = await self.dictionary.version(tenant_id, DictionaryStatus.ACTIVE)
        if active is None:
            raise dictionary_not_imported()
        return active

    # ------------------------------------------------------------------ reading

    async def state(self, context: RequestContext) -> DictionaryState:
        _actor, tenant_id = await self._manager(context)
        active = await self.dictionary.version(tenant_id, DictionaryStatus.ACTIVE)
        previous = await self.dictionary.version(tenant_id, DictionaryStatus.PREVIOUS)
        importers = await self.dictionary.importers(
            {v.created_by for v in (active, previous) if v is not None and v.created_by}
        )
        serving = self.index.serving
        return DictionaryState(
            active=(
                ActiveDictionaryVersion(
                    **_summary(active, importers).model_dump(),
                    warnings=list(active.warnings),
                )
                if active
                else None
            ),
            previous=_summary(previous, importers) if previous else None,
            index_dictionary_version=(serving.engine.dictionary.version if serving else ""),
        )

    async def tables(
        self, context: RequestContext, page: int, page_size: int
    ) -> DictionaryTablesPage:
        _actor, tenant_id = await self._manager(context)
        active = await self._active(tenant_id)
        profiles = object_profiles(await self.dictionary.objects(active))
        counts = sorted(await self.dictionary.table_counts(active), key=lambda t: t.key)
        start = (page - 1) * page_size
        items = []
        for table in counts[start : start + page_size]:
            profile = profiles.get(table.key)
            items.append(
                DictionaryTable(
                    key=table.key,
                    name=table.key.rsplit(".", 1)[-1],
                    group=profile.group if profile else "",
                    domain=profile.domain if profile else "",
                    description=profile.description if profile else "",
                    grain=profile.grain if profile else "",
                    columns=table.columns,
                )
            )
        return DictionaryTablesPage(items=items, total=len(counts), page=page, page_size=page_size)

    async def table(self, context: RequestContext, key: str) -> DictionaryTableRecords:
        _actor, tenant_id = await self._manager(context)
        active = await self._active(tenant_id)
        columns = await self.dictionary.table_columns(active, key)
        if not columns:
            raise ApplicationError(
                status.HTTP_404_NOT_FOUND,
                "dictionary_table_not_found",
                "Tablo sözlükte yok.",
            )
        record = next(
            (
                o
                for o in await self.dictionary.objects(active)
                if (
                    o.get("ObjectKey") or f"{o['DatabaseName']}.{o['SchemaName']}.{o['ObjectName']}"
                )
                == key
            ),
            None,
        )
        return DictionaryTableRecords(key=key, object=record, columns=columns)

    # ------------------------------------------------------------------ downloads

    async def export(self, context: RequestContext) -> tuple[str, bytes]:
        actor, tenant_id = await self._manager(context)
        active = await self._active(tenant_id)
        objects = await self.dictionary.objects(active)
        columns = await self.dictionary.columns(active)
        data = await asyncio.to_thread(export, objects, columns)
        log_event(
            logger,
            "dictionary.export",
            kind="dictionary",
            version=active.version,
            user_public_id=actor.public_id,
        )
        telemetry.record_dictionary_export("dictionary")
        return export_filename(datetime.now(UTC)), data
