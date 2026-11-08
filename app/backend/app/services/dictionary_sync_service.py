"""The admin screen's dictionary update: source, runs, report, versions (011-dictionary-sync).

Every call re-reads the acting account and requires ``yonetici``. The password is sealed for its
address: changing the host or port without a new password drops the saved one, and no response
carries it.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.domain.accounts import ROLE_MANAGER
from app.domain.dictionary import VERSION_RETENTION_DAYS, DictionaryStatus
from app.domain.dictionary_source import SourceInvalid, SourceUnavailable
from app.domain.models.dictionary import DictionaryVersion
from app.domain.models.dictionary_sync import DictionarySource, DictionarySyncRun
from app.domain.models.tenant import Tenant
from app.domain.models.user import User
from app.domain.vocabulary import VocabularyList
from app.infrastructure.repositories.dictionary_repository import DictionaryRepository
from app.infrastructure.repositories.dictionary_sync_repository import (
    DictionarySyncRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.dictionary.sync import (
    ApplySuggestions,
    Change,
    ChangesPage,
    Counts,
    Person,
    RecordEdit,
    RunDetail,
    RunsPage,
    RunSummary,
    Source,
    SourceInput,
    SourceTest,
    Suggestion,
    SyncPreview,
    Version,
    VersionsPage,
)
from app.services.analysis.dictionary_workbook import records_digest
from app.services.dictionary_curation.score import rescored, tables_of
from app.services.dictionary_sync import (
    SOURCE_INVALID_MESSAGE,
    SOURCE_UNAVAILABLE_MESSAGE,
    DictionarySync,
    connection_of,
    remember,
    run_in_progress,
    source_not_configured,
)
from app.services.dictionary_sync_fill import ROLES, SUMMARY_MAX_CHARS
from app.services.dictionary_sync_merge import ORIGIN_ADMIN
from app.services.dictionary_sync_merge import Change as SyncChange
from app.services.request_scope import acting_user_with_role, active_tenant
from app.services.search_index import SearchIndex
from app.services.vocabulary_service import VocabularyService

SUGGESTION_GROUP = "Sözlük önerisi"
KEPT_STATUSES = {"active", "previous", "pending"}


def _not_found(what: str) -> ApplicationError:
    return ApplicationError(status.HTTP_404_NOT_FOUND, "not_found", f"{what} bulunamadı.")


COLUMN_EDIT_FIELDS = frozenset({"ColumnDescription", "Synonyms", "Summary", "Role"})
OBJECT_EDIT_FIELDS = frozenset({"ObjectDescription", "Grain", "KeyColumns", "TimeColumns", "BusinessDomain"})


def _bad_edit(message: str) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, "dictionary_edit_invalid", message)


def _no_record() -> ApplicationError:
    return ApplicationError(
        status.HTTP_404_NOT_FOUND, "dictionary_record_not_found", "Bu kayıt bekleyen sürümde yok."
    )


def _not_pending() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT, "dictionary_run_not_pending", "Bu güncelleme onay beklemiyor."
    )


def _expired() -> ApplicationError:
    return ApplicationError(
        status.HTTP_410_GONE,
        "dictionary_version_expired",
        "Bu sürümün saklama süresi doldu.",
    )


def _no_encryption() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "settings_encryption_unavailable",
        "Parola saklanamıyor: DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY tanımlı değil.",
    )


class DictionarySyncService:
    def __init__(self, session: AsyncSession, sync: DictionarySync, index: SearchIndex) -> None:
        self.session = session
        self.sync = sync
        self.index = index
        self.users = UserRepository(session)
        self.runs = DictionarySyncRepository(session)
        self.dictionary = DictionaryRepository(session)

    async def _manager(self, context: RequestContext) -> tuple[User, Tenant]:
        actor = await acting_user_with_role(self.users, context, ROLE_MANAGER)
        return actor, await active_tenant(self.users, context)

    # ------------------------------------------------------------------ source

    @staticmethod
    def _source(row: DictionarySource | None) -> Source:
        if row is None:
            return Source(
                configured=False,
                host="",
                port=1433,
                database="EDWUTIL",
                username="",
                has_password=False,
                encrypt=False,
                updated_at=None,
            )
        return Source(
            configured=row.password_ciphertext is not None,
            host=row.host,
            port=row.port,
            database=row.database_name,
            username=row.username,
            has_password=row.password_ciphertext is not None,
            encrypt=row.encrypt,
            updated_at=row.updated_at,
        )

    async def source(self, context: RequestContext) -> Source:
        _actor, tenant = await self._manager(context)
        return self._source(await self.runs.source(tenant.tenant_id))

    async def save_source(self, context: RequestContext, body: SourceInput) -> Source:
        actor, tenant = await self._manager(context)
        keys = self.sync.keys()
        if body.password and not keys.available:
            raise _no_encryption()
        row = await self.runs.source(tenant.tenant_id)
        now = datetime.now(UTC)
        if row is None:
            row = DictionarySource(
                tenant_id=tenant.tenant_id,
                host=body.host,
                port=body.port,
                database_name=body.database,
                username=body.username,
                encrypt=body.encrypt,
                created_at=now,
                updated_at=now,
                created_by=actor.user_id,
                updated_by=actor.user_id,
            )
            self.session.add(row)
            await self.session.flush()
        else:
            if (row.host, row.port) != (body.host, body.port):
                row.password_ciphertext = None
            row.host = body.host
            row.port = body.port
            row.database_name = body.database
            row.username = body.username
            row.encrypt = body.encrypt
            row.updated_at = now
            row.updated_by = actor.user_id
        if body.password:
            row.password_ciphertext = keys.seal(
                body.password, tenant_public_id=tenant.public_id, row=row
            )
        await self.session.commit()
        await self.session.refresh(row)
        return self._source(row)

    async def test_source(self, context: RequestContext, body: SourceInput) -> SourceTest:
        _actor, tenant = await self._manager(context)
        row = await self.runs.source(tenant.tenant_id)
        password = body.password
        if not password and row is not None and (row.host, row.port) == (body.host, body.port):
            password = self.sync.keys().open(row, tenant_public_id=tenant.public_id)
        if not password:
            raise source_not_configured()
        trial = DictionarySource(
            host=body.host,
            port=body.port,
            database_name=body.database,
            username=body.username,
            encrypt=body.encrypt,
        )
        try:
            probe = await self.sync.source.probe(connection_of(trial, password))
        except SourceUnavailable:
            return SourceTest(
                ok=False,
                message=SOURCE_UNAVAILABLE_MESSAGE,
                table_count=0,
                column_count=0,
                last_change_at=None,
            )
        except SourceInvalid:
            return SourceTest(
                ok=False,
                message=SOURCE_INVALID_MESSAGE,
                table_count=0,
                column_count=0,
                last_change_at=None,
            )
        missing = list(probe.missing_databases)
        return SourceTest(
            ok=not missing,
            message=(
                "Şu veritabanları okunamıyor: " + ", ".join(missing)
                if missing
                else "Bağlantı başarılı."
            ),
            table_count=probe.table_count,
            column_count=probe.column_count,
            last_change_at=probe.last_change_at,
            missing_databases=missing,
        )

    # ------------------------------------------------------------------ runs

    async def _people(self, user_ids: set[int]) -> dict[int, Person]:
        found = await self.dictionary.importers(user_ids)
        return {uid: Person(public_id=p, display_name=n) for uid, (p, n) in found.items()}

    @staticmethod
    def _summary(run: DictionarySyncRun, people: dict[int, Person]) -> dict[str, Any]:
        return {
            "public_id": run.public_id,
            "kind": run.kind,
            "status": run.status,
            "phase": run.phase,
            "progress_done": run.progress_done,
            "progress_total": run.progress_total,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "started_by": people.get(run.created_by) if run.created_by else None,
            "previous_version": run.previous_version,
            "new_version": run.new_version,
            "model": run.model,
            "counts": Counts(**run.counts),
            "score": run.score or {},
            "error_code": run.error_code,
            "error_message": run.error_message,
        }

    async def _detail(self, run: DictionarySyncRun) -> RunDetail:
        people = await self._people({run.created_by} if run.created_by else set())
        suggestions = await self.runs.suggestions(run.dictionary_sync_run_id)
        return RunDetail(
            **self._summary(run, people),
            warnings=list(run.warnings),
            suggestions=[
                Suggestion(
                    public_id=s.public_id,
                    kind=s.kind,  # type: ignore[arg-type]
                    value=s.value,
                    equivalents=list(s.equivalents),
                    note=s.note,
                    status=s.status,  # type: ignore[arg-type]
                )
                for s in suggestions
            ],
        )

    async def _run(self, tenant: Tenant, public_id: str) -> DictionarySyncRun:
        run = await self.runs.run(tenant.tenant_id, public_id)
        if run is None:
            raise _not_found("Güncelleme")
        return run

    async def _summary_of(self, tenant: Tenant, public_id: str) -> RunSummary:
        run = await self._run(tenant, public_id)
        people = await self._people({run.created_by} if run.created_by else set())
        return RunSummary(**self._summary(run, people))

    async def preview(self, context: RequestContext) -> SyncPreview:
        _actor, tenant = await self._manager(context)
        return SyncPreview(**await self.sync.preview(tenant.tenant_id, tenant.public_id))

    async def start(self, context: RequestContext) -> RunSummary:
        actor, tenant = await self._manager(context)
        public_id = await self.sync.start_update(tenant.tenant_id, tenant.public_id, actor.user_id)
        return await self._summary_of(tenant, public_id)

    async def list_runs(self, context: RequestContext, page: int, page_size: int) -> RunsPage:
        _actor, tenant = await self._manager(context)
        runs, total = await self.runs.runs(tenant.tenant_id, page, page_size)
        people = await self._people({r.created_by for r in runs if r.created_by})
        return RunsPage(
            items=[RunSummary(**self._summary(r, people)) for r in runs],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def run(self, context: RequestContext, public_id: str) -> RunDetail:
        _actor, tenant = await self._manager(context)
        return await self._detail(await self._run(tenant, public_id))

    async def changes(
        self,
        context: RequestContext,
        public_id: str,
        kind: str,
        search: str,
        page: int,
        page_size: int,
    ) -> ChangesPage:
        _actor, tenant = await self._manager(context)
        run = await self._run(tenant, public_id)
        rows, total = await self.runs.changes(
            run.dictionary_sync_run_id, kind, search, page, page_size
        )
        return ChangesPage(
            items=[
                Change(
                    kind=r.kind,
                    table_key=r.table_key,
                    column_name=r.column_name,
                    field=r.field,
                    old_value=r.old_value,
                    new_value=r.new_value,
                    origin=r.origin,
                )
                for r in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def _waiting(
        self, tenant: Tenant, public_id: str
    ) -> tuple[DictionarySyncRun, DictionaryVersion]:
        run = await self._run(tenant, public_id)
        version = (
            await self.session.get(DictionaryVersion, run.dictionary_version_id)
            if run.dictionary_version_id
            else None
        )
        if (
            run.status != "pending_approval"
            or version is None
            or version.status != DictionaryStatus.PENDING.value
        ):
            raise _not_pending()
        return run, version

    async def approve(self, context: RequestContext, public_id: str) -> RunDetail:
        actor, tenant = await self._manager(context)
        run, version = await self._waiting(tenant, public_id)
        run_id = run.dictionary_sync_run_id
        version_id = version.dictionary_version_id
        objects = await self.dictionary.objects(version)
        columns = await self.dictionary.columns(version)
        number, digest = version.version, version.content_digest
        user_id = actor.user_id
        now = datetime.now(UTC)

        async def write(session: AsyncSession) -> None:
            repository = DictionaryRepository(session)
            if not await repository.try_import_lock():
                raise run_in_progress()
            target = await session.get(DictionaryVersion, version_id)
            assert target is not None
            await repository.activate(target, user_id=user_id, now=now)
            stored = await DictionarySyncRepository(session).run_by_id(run_id)
            stored.status = "completed"
            stored.finished_at = now
            # The trail digests waited with the version: from now on the next update compares
            # against them.
            waiting = {(t, c): d for t, c, d in stored.pending_digests or []}
            if waiting:
                await remember(session, tenant.tenant_id, waiting, None)
            stored.pending_digests = []

        await self.sync.swap(objects, columns, number, digest, write)
        await self.session.refresh(run)
        return await self._detail(run)

    async def edit_record(
        self, context: RequestContext, public_id: str, body: RecordEdit
    ) -> RunDetail:
        """An admin's text in the version waiting for approval; no update or rule rewrites it."""

        actor, tenant = await self._manager(context)
        run, version = await self._waiting(tenant, public_id)
        fields = COLUMN_EDIT_FIELDS if body.column_name else OBJECT_EDIT_FIELDS
        if body.field not in fields:
            raise _bad_edit("Bu alan bu kayıtta düzenlenemez.")
        value = " ".join(body.value.split())
        if body.field == "Role" and value not in ROLES:
            raise _bad_edit("Rol şunlardan biri olmalı: " + ", ".join(ROLES) + ".")
        if body.field == "Summary" and len(value) > SUMMARY_MAX_CHARS:
            raise _bad_edit(f"Özet en çok {SUMMARY_MAX_CHARS} karakter olabilir.")
        if body.field in ("ColumnDescription", "ObjectDescription") and not value:
            raise _bad_edit("Açıklama boş bırakılamaz.")
        old = await self.dictionary.edit_record(
            version, body.table_key, body.column_name, body.field, value, ORIGIN_ADMIN
        )
        if old is None:
            raise _no_record()
        objects = await self.dictionary.objects(version)
        columns = await self.dictionary.columns(version)
        digest = records_digest(objects, columns)
        version.content_digest = digest
        version.version = f"{digest}-{len(columns)}"
        run.new_version = version.version
        # The checks follow the edit: a fixed row no longer counts against the version.
        card = rescored(run.score or {}, tables_of(objects, columns), self.sync.decisions)
        run.score = {**card, "admin_edits": int((run.score or {}).get("admin_edits", 0)) + 1}
        await self.runs.append_change(
            run.dictionary_sync_run_id,
            SyncChange(
                "column_admin_edited" if body.column_name else "table_admin_edited",
                body.table_key,
                body.column_name,
                body.field,
                old,
                value,
                ORIGIN_ADMIN,
            ),
        )
        run.updated_by = actor.user_id
        await self.session.commit()
        return await self._detail(await self._run(tenant, public_id))

    async def reject(self, context: RequestContext, public_id: str) -> RunDetail:
        actor, tenant = await self._manager(context)
        run, version = await self._waiting(tenant, public_id)
        now = datetime.now(UTC)
        await self.dictionary.prune(version, user_id=actor.user_id, now=now)
        run.status = "rejected"
        run.finished_at = now
        await self.session.commit()
        return await self._detail(await self._run(tenant, public_id))

    async def apply_suggestions(
        self, context: RequestContext, public_id: str, body: ApplySuggestions
    ) -> RunDetail:
        _actor, tenant = await self._manager(context)
        run = await self._run(tenant, public_id)
        chosen = {
            s.public_id: s
            for s in await self.runs.suggestions(run.dictionary_sync_run_id)
            if s.public_id in set(body.suggestion_ids) and s.status == "pending"
        }
        vocabulary = VocabularyService(self.session, self.index)
        terms = [s for s in chosen.values() if s.kind == "term"]
        words = [s for s in chosen.values() if s.kind == "stopword"]
        ids = [s.dictionary_sync_suggestion_id for s in chosen.values()]
        term_items = [
            {"term": s.value, "equivalents": list(s.equivalents), "domain": "", "note": s.note}
            for s in terms
        ]
        word_items = [{"word": s.value, "group": SUGGESTION_GROUP} for s in words]
        if term_items:
            state = await vocabulary.read(context, VocabularyList.TERMS)
            current = [i.model_dump() for i in state.items]
            await vocabulary.save(context, VocabularyList.TERMS, [*current, *term_items])
        if word_items:
            state = await vocabulary.read(context, VocabularyList.STOPWORDS)
            current = [i.model_dump() for i in state.items]
            await vocabulary.save(context, VocabularyList.STOPWORDS, [*current, *word_items])
        for suggestion in await self.runs.suggestions(run.dictionary_sync_run_id):
            if suggestion.dictionary_sync_suggestion_id in ids:
                suggestion.status = "applied"
        await self.session.commit()
        return await self._detail(await self._run(tenant, public_id))

    # ------------------------------------------------------------------ versions

    async def versions(self, context: RequestContext) -> VersionsPage:
        _actor, tenant = await self._manager(context)
        rows = [
            v
            for v in await self.dictionary.kept_versions(tenant.tenant_id)
            if v.status in KEPT_STATUSES
        ]
        people = await self._people({v.created_by for v in rows if v.created_by})
        links = await self.runs.runs_of_versions([v.dictionary_version_id for v in rows])
        return VersionsPage(
            items=[
                Version(
                    public_id=v.public_id,
                    version=v.version,
                    status=v.status,  # type: ignore[arg-type]
                    channel=v.channel,
                    imported_at=v.imported_at,
                    imported_by=people.get(v.created_by) if v.created_by else None,
                    object_count=v.object_count,
                    column_count=v.column_count,
                    run_public_id=links.get(v.dictionary_version_id),
                    expires_at=(
                        v.superseded_at + timedelta(days=VERSION_RETENTION_DAYS)
                        if v.superseded_at
                        else None
                    ),
                    can_restore=v.status == DictionaryStatus.PREVIOUS.value,
                )
                for v in rows
            ]
        )

    async def restore(self, context: RequestContext, public_id: str) -> RunSummary:
        actor, tenant = await self._manager(context)
        version = await self.dictionary.by_public_id(tenant.tenant_id, public_id)
        if version is None:
            raise _not_found("Sürüm")
        if version.status != DictionaryStatus.PREVIOUS.value:
            raise _expired()
        started = await self.sync.start_restore(
            tenant.tenant_id, version.dictionary_version_id, actor.user_id
        )
        return await self._summary_of(tenant, started)
