"""The Kelimeler page: read, save, export and import a word list (vocabulary-management).

data-dictionary/PRDs/002-vocabulary-management Requirement 1, 3-8, 14 and 15. Every request
re-reads the acting account and requires ``yonetici``. A save is checked before it waits for
anything; then it goes through the search index's change queue: the same content writes nothing
(``changed: false``); otherwise the engine is built with the new list first and the list is
written in one transaction (old rows soft-deleted, new rows inserted, revision raised), so the
new list and the new engine serve together or not at all. Two saves of the same list run one
after the other and the later one wins (Decision 5). No list content reaches a log line.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError, validation_message
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.domain.accounts import ROLE_MANAGER
from app.domain.models.user import User
from app.domain.vocabulary import (
    VocabularyList,
    VocabularyRejected,
    VocabularyShapeError,
    VocabularySource,
    check_list,
    list_digest,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.repositories.vocabulary_repository import VocabularyRepository
from app.schemas.vocabulary.lists import (
    StopwordItem,
    TermItem,
    VocabularyListSaved,
    VocabularyListState,
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
from app.services.search_inputs import SearchInputs
from app.services.search_status import index_state
from app.services.vocabulary_reading import stopword_forms, term_groups
from app.services.vocabulary_workbook import (
    FILENAME_PREFIXES,
    items_from_workbook,
    items_to_workbook,
)

logger = logging.getLogger("app.vocabulary")

ISTANBUL = ZoneInfo("Europe/Istanbul")


def list_not_found() -> ApplicationError:
    return ApplicationError(
        status.HTTP_404_NOT_FOUND, "vocabulary_list_not_found", "Kayıt bulunamadı"
    )


def parse_list_name(raw: str) -> VocabularyList:
    try:
        return VocabularyList(raw)
    except ValueError:
        raise list_not_found() from None


def _rejected(error: VocabularyRejected) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, error.code, error.message)


def _shape_error(error: VocabularyShapeError) -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_request",
        validation_message([error.location]),
    )


def _items_schema(kind: VocabularyList, items: list[dict[str, Any]]) -> list[Any]:
    if kind is VocabularyList.TERMS:
        return [TermItem(**item) for item in items]
    return [StopwordItem(**item) for item in items]


@dataclass(slots=True)
class _SaveResult:
    changed: bool = False
    revision: int = 0


class VocabularyService:
    def __init__(self, session: AsyncSession, index: SearchIndex) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.lists = VocabularyRepository(session)
        self.index = index

    async def _manager(self, context: RequestContext) -> tuple[User, int]:
        actor = await acting_user_with_role(self.users, context, ROLE_MANAGER)
        tenant = await active_tenant(self.users, context)
        return actor, tenant.tenant_id

    async def _state(
        self, tenant_id: int, kind: VocabularyList
    ) -> tuple[int, list[dict[str, Any]]]:
        header = await self.lists.header(tenant_id, kind)
        if header is None:
            raise list_not_found()
        return header.revision, await self.lists.items(tenant_id, kind)

    async def read(self, context: RequestContext, kind: VocabularyList) -> VocabularyListState:
        _actor, tenant_id = await self._manager(context)
        revision, items = await self._state(tenant_id, kind)
        return VocabularyListState.model_validate(
            {"list": kind.value, "revision": revision, "items": _items_schema(kind, items)}
        )

    async def export(self, context: RequestContext, kind: VocabularyList) -> tuple[str, bytes]:
        _actor, tenant_id = await self._manager(context)
        _revision, items = await self._state(tenant_id, kind)
        data = await asyncio.to_thread(items_to_workbook, kind, items)
        stamp = datetime.now(UTC).astimezone(ISTANBUL)
        return f"{FILENAME_PREFIXES[kind]}_{stamp:%Y%m%d_%H%M}.xlsx", data

    async def save(
        self, context: RequestContext, kind: VocabularyList, items: object
    ) -> VocabularyListSaved:
        actor, tenant_id = await self._manager(context)
        return await self._replace(
            actor,
            tenant_id,
            kind,
            items,
            VocabularySource.SCREEN,
            started=perf_counter(),
        )

    async def import_workbook(
        self,
        context: RequestContext,
        kind: VocabularyList,
        read_upload: Callable[[], Awaitable[bytes]],
    ) -> VocabularyListSaved:
        actor, tenant_id = await self._manager(context)
        started = perf_counter()
        try:
            data = await read_upload()
        except ApplicationError as refused:
            self._log_rejected(kind, VocabularySource.EXCEL, refused.code)
            raise
        try:
            items = await asyncio.to_thread(items_from_workbook, kind, data)
        except VocabularyRejected as rejected:
            self._log_rejected(kind, VocabularySource.EXCEL, rejected.code)
            raise _rejected(rejected) from None
        return await self._replace(
            actor, tenant_id, kind, items, VocabularySource.EXCEL, started=started
        )

    async def _replace(
        self,
        actor: User,
        tenant_id: int,
        kind: VocabularyList,
        raw_items: object,
        source: VocabularySource,
        *,
        started: float,
    ) -> VocabularyListSaved:
        try:
            items = check_list(kind, raw_items)
        except VocabularyRejected as rejected:
            self._log_rejected(kind, source, rejected.code)
            raise _rejected(rejected) from None
        except VocabularyShapeError as shape:
            self._log_rejected(kind, source, "invalid_request")
            raise _shape_error(shape) from None
        if tenant_id != await self.index.tenant_id():
            raise forbidden()
        digest = list_digest(items)
        result = _SaveResult()
        now = datetime.now(UTC)

        async def plan(inputs: SearchInputs, _serving: ServingEngine | None) -> ChangePlan:
            current = (
                inputs.identity.terms
                if kind is VocabularyList.TERMS
                else (inputs.identity.stopwords)
            )
            if current == digest:
                return ChangePlan(result=result)
            if kind is VocabularyList.TERMS:
                new_inputs = inputs.replace(
                    term_groups=tuple(term_groups(items)), terms_identity=digest
                )
            else:
                new_inputs = inputs.replace(
                    stopwords=stopword_forms(items), stopwords_identity=digest
                )

            async def write(session: AsyncSession) -> None:
                repository = VocabularyRepository(session)
                header = await repository.header(tenant_id, kind, for_update=True)
                if header is None:
                    raise list_not_found()
                result.revision = await repository.replace(
                    header,
                    items,
                    digest=digest,
                    source=source.value,
                    user_id=actor.user_id,
                    now=now,
                )
                result.changed = True

            return ChangePlan(inputs=new_inputs, write=write, result=result)

        trigger = IndexTrigger.TERMS if kind is VocabularyList.TERMS else IndexTrigger.STOPWORDS
        try:
            await self.index.change(trigger, plan)
        except SearchChangeBusy:
            self._log_rejected(kind, source, "search_change_busy")
            raise search_change_busy() from None
        except SearchIndexBuildFailed:
            self._log_rejected(kind, source, "search_index_build_failed")
            raise search_index_build_failed() from None
        revision, stored = await self._state(tenant_id, kind)
        elapsed_ms = round((perf_counter() - started) * 1000)
        log_event(
            logger,
            "vocabulary.saved",
            list=kind.value,
            source=source.value,
            items=len(stored),
            revision=revision,
            changed=result.changed,
            duration_ms=elapsed_ms,
            user_public_id=actor.public_id,
        )
        return VocabularyListSaved.model_validate(
            {
                "list": kind.value,
                "revision": revision,
                "items": _items_schema(kind, stored),
                "changed": result.changed,
                "elapsed_ms": elapsed_ms,
                "index": await index_state(self.index),
            }
        )

    @staticmethod
    def _log_rejected(kind: VocabularyList, source: VocabularySource, code: str) -> None:
        log_event(
            logger,
            "vocabulary.rejected",
            list=kind.value,
            source=source.value,
            code=code,
        )
