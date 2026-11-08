"""The admin screen's dictionary: state, tables, import, export and template (001).

data-dictionary/PRDs/001-dictionary-management Requirement 2-15, 17, 18. Every request re-reads the
acting account and requires ``yonetici`` (the super admin passes); the router checks the same role.
An import is read and checked before it waits for anything (Decision 11), then goes through the
search index's change queue: the new engine is built from the new dictionary first and the version
is written only when the build succeeded (Requirement 9). The write takes the PostgreSQL import
lock without waiting (409 ``dictionary_import_in_progress``). The same content creates no version
(Requirement 7). An import replaces the whole dictionary, as before the warehouse update; it is
refused while an update or a rollback runs (409 ``dictionary_sync_in_progress``) and drops an
update still waiting for approval, which was merged onto the replaced version (dictionary-sync
Requirement 13). No dictionary content, file name or warning reaches a log line, metric or span.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import perf_counter
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
    MAX_KEPT_WARNINGS,
    VERSION_RETENTION_DAYS,
    DictionaryStatus,
    ImportChannel,
)
from app.domain.models.dictionary import DictionaryVersion
from app.domain.models.user import User
from app.infrastructure.repositories.dictionary_repository import (
    DictionaryRepository,
    NewDictionaryVersion,
)
from app.infrastructure.repositories.dictionary_sync_repository import (
    DictionarySyncRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.dictionary.management import (
    ActiveDictionaryVersion,
    DictionaryImported,
    DictionaryImporter,
    DictionaryState,
    DictionaryTable,
    DictionaryTableRecords,
    DictionaryTablesPage,
    DictionaryVersionSummary,
)
from app.services.analysis.dictionary_workbook import export, load_dictionary
from app.services.analysis.loader import object_profiles
from app.services.dictionary_import import (
    CheckedDictionary,
    DictionaryWorkbookInvalid,
    check_dictionary_workbook,
)
from app.services.dictionary_reading import dictionary_identity, identity_digest
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
from app.services.search_inputs import SearchInputs
from app.services.search_status import index_state

logger = logging.getLogger("app.dictionary")

ISTANBUL = ZoneInfo("Europe/Istanbul")
TEMPLATE_FILENAME = "VeriSozlugu_sablon.xlsx"
WORKBOOK_INVALID_CODE = "dictionary_workbook_invalid"
SYNC_IN_PROGRESS_CODE = "dictionary_sync_in_progress"
SYNC_IN_PROGRESS_MESSAGE = "Bir sözlük güncellemesi sürüyor; bitince yeniden deneyin."

# Upload refusals of the HTTP boundary -> the import outcome class of the PRD's signals.
_UPLOAD_OUTCOMES = {
    "upload_too_large": "too_large",
    "unsupported_media_type": "unsupported_type",
    "dictionary_file_empty": "invalid",
}


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


def _sync_in_progress() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT, SYNC_IN_PROGRESS_CODE, SYNC_IN_PROGRESS_MESSAGE
    )


def _workbook_invalid(invalid: DictionaryWorkbookInvalid) -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, WORKBOOK_INVALID_CODE, invalid.message
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


def new_version(
    checked: CheckedDictionary,
    *,
    source_name: str,
    channel: ImportChannel,
    now: datetime,
) -> NewDictionaryVersion:
    imported = checked.imported
    return NewDictionaryVersion(
        version=imported.version,
        content_digest=imported.digest,
        source_name=source_name,
        channel=channel.value,
        imported_at=now,
        row_count=checked.row_count,
        column_count=imported.column_count,
        object_count=imported.object_count,
        warnings=imported.warnings[:MAX_KEPT_WARNINGS],
        warning_count=len(imported.warnings),
        objects=imported.objects,
        columns=imported.columns,
        object_extra_headers=checked.object_extra_headers,
        column_extra_headers=checked.column_extra_headers,
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


async def replace_with_import(
    session: AsyncSession,
    tenant_id: int,
    version: NewDictionaryVersion,
    *,
    user_id: int | None,
    now: datetime,
) -> DictionaryVersion:
    """Write an imported workbook as the active version (dictionary-sync Requirement 13).

    Refused while an update or a rollback runs; an update waiting for approval is rejected and its
    version pruned, since it was merged onto the version this import replaces. Replaced versions
    past the retention are pruned as after an update.
    """

    runs = DictionarySyncRepository(session)
    if await runs.is_running(tenant_id):
        raise _sync_in_progress()
    written = await write_dictionary_version(session, tenant_id, version, user_id=user_id, now=now)
    repository = DictionaryRepository(session)
    for run in await runs.pending_runs(tenant_id):
        waiting = await repository.version(tenant_id, DictionaryStatus.PENDING)
        if waiting is not None:
            await repository.prune(waiting, user_id=user_id, now=now)
        run.status = "rejected"
        run.finished_at = now
        run.updated_at = now
        run.updated_by = user_id
        log_event(logger, "dictionary.waiting_rejected", reason="import")
    pruned = await repository.prune_expired(
        tenant_id, before=now - timedelta(days=VERSION_RETENTION_DAYS), now=now
    )
    if pruned:
        log_event(logger, "dictionary.pruned_expired", versions=pruned)
    return written


class _ImportRefused(Exception):
    def __init__(self, outcome: str, error: ApplicationError) -> None:
        super().__init__(error.code)
        self.outcome = outcome
        self.error = error


@dataclass(slots=True)
class _ImportResult:
    written: DictionaryVersion | None = None
    warnings: list[str] = field(default_factory=list)


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

    async def template(self, context: RequestContext) -> tuple[str, bytes]:
        actor, _tenant_id = await self._manager(context)
        data = await asyncio.to_thread(export, None, None)
        log_event(
            logger,
            "dictionary.export",
            kind="template",
            version="",
            user_public_id=actor.public_id,
        )
        telemetry.record_dictionary_export("template")
        return TEMPLATE_FILENAME, data

    # ------------------------------------------------------------------ import

    async def import_workbook(
        self,
        context: RequestContext,
        read_upload: Callable[[], Awaitable[tuple[str, bytes]]],
    ) -> DictionaryImported:
        """Requirement 2-9: read, check, then build and write through the change queue."""

        actor, tenant_id = await self._manager(context)
        started = perf_counter()
        checked: CheckedDictionary | None = None
        with telemetry.dictionary_import_span(ImportChannel.SCREEN) as span:
            try:
                try:
                    source_name, data = await read_upload()
                except ApplicationError as refused:
                    raise _ImportRefused(_UPLOAD_OUTCOMES.get(refused.code, "error"), refused)
                try:
                    checked = await asyncio.to_thread(check_dictionary_workbook, data)
                except DictionaryWorkbookInvalid as invalid:
                    raise _ImportRefused("invalid", _workbook_invalid(invalid)) from None
                span.row_count = checked.row_count
                if tenant_id != await self.index.tenant_id():
                    raise _ImportRefused("error", forbidden())
                if await DictionarySyncRepository(self.session).is_running(tenant_id):
                    raise _ImportRefused("conflict", _sync_in_progress())
                try:
                    result = await self._apply(checked, source_name, actor, tenant_id)
                except ApplicationError as refused:
                    conflict = refused.code in (
                        "dictionary_import_in_progress",
                        SYNC_IN_PROGRESS_CODE,
                    )
                    raise _ImportRefused("conflict" if conflict else "error", refused) from None
            except _ImportRefused as refused:
                span.outcome = refused.outcome
                self._log_import(refused.outcome, refused.error.code, checked, actor, started)
                raise refused.error from None
            outcome = "created" if result.written is not None else "unchanged"
            span.outcome = outcome
        self._log_import(outcome, "", checked, actor, started)
        return await self._import_answer(result, tenant_id)

    async def _apply(
        self, checked: CheckedDictionary, source_name: str, actor: User, tenant_id: int
    ) -> _ImportResult:
        imported = checked.imported
        result = _ImportResult(warnings=imported.warnings[:MAX_KEPT_WARNINGS])
        now = datetime.now(UTC)
        version = new_version(
            checked, source_name=source_name, channel=ImportChannel.SCREEN, now=now
        )

        async def plan(inputs: SearchInputs, serving: ServingEngine | None) -> ChangePlan:
            if inputs.identity.dictionary and identity_digest(inputs.identity.dictionary) == (
                imported.digest
            ):
                # Decision 6: the same content changes nothing; a stale index is rebuilt.
                if serving is None or serving.identity.dictionary != inputs.identity.dictionary:
                    return ChangePlan(inputs=inputs, result=result)
                return ChangePlan(result=result)
            dictionary = load_dictionary(
                imported.objects, imported.columns, imported.version, imported.digest
            )
            new_inputs = inputs.replace(
                dictionary=dictionary,
                dictionary_identity=dictionary_identity(imported.version, imported.digest),
            )

            async def write(session: AsyncSession) -> None:
                result.written = await replace_with_import(
                    session, tenant_id, version, user_id=actor.user_id, now=now
                )

            return ChangePlan(inputs=new_inputs, write=write, result=result)

        try:
            outcome = await self.index.change(IndexTrigger.DICTIONARY, plan)
        except SearchChangeBusy:
            raise search_change_busy() from None
        except SearchIndexBuildFailed:
            raise search_index_build_failed() from None
        imported_result: _ImportResult = outcome.result
        return imported_result

    async def _import_answer(self, result: _ImportResult, tenant_id: int) -> DictionaryImported:
        if result.written is not None:
            version = result.written
            warnings = result.warnings
        else:
            version = await self._active(tenant_id)
            warnings = list(version.warnings)
        importers = await self.dictionary.importers(
            {version.created_by} if version.created_by else set()
        )
        return DictionaryImported(
            changed=result.written is not None,
            version=_summary(version, importers),
            warnings=warnings,
            index=await index_state(self.index),
        )

    @staticmethod
    def _log_import(
        outcome: str,
        code: str,
        checked: CheckedDictionary | None,
        actor: User,
        started: float,
    ) -> None:
        imported = checked.imported if checked else None
        log_event(
            logger,
            "dictionary.import",
            outcome=outcome,
            channel=ImportChannel.SCREEN.value,
            version=imported.version if imported else "",
            row_count=checked.row_count if checked else 0,
            column_count=imported.column_count if imported else 0,
            object_count=imported.object_count if imported else 0,
            warning_count=len(imported.warnings) if imported else 0,
            duration_ms=round((perf_counter() - started) * 1000),
            error_code=code,
            user_public_id=actor.public_id,
        )
