"""The dictionary's single read function (dictionary-management Requirement 10, 11 and 17).

Every capability that reads the dictionary, the search index first of all, reads the active
version through ``read_dictionary``: its Objeler and Kolonlar records in sheet order and in the
source's record shape, parsed by the source's code into the engine's ``Dictionary``. The content
digest is recomputed on every read; records changed by hand give the version
``<new digest>-<Kolonlar record count>`` and a ``dictionary.integrity_mismatch`` event. Without an
active version the dictionary is empty: no column, version ``""``, source ``dictionary.jsonl``.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log_event
from app.domain.analysis import Dictionary
from app.domain.dictionary import DictionaryStatus
from app.domain.models.dictionary import DictionaryVersion
from app.infrastructure.repositories.dictionary_repository import DictionaryRepository
from app.services.analysis.dictionary_workbook import (
    empty_dictionary,
    load_dictionary,
    records_digest,
)

logger = logging.getLogger("app.dictionary")


@dataclass(frozen=True, slots=True)
class DictionaryRead:
    dictionary: Dictionary
    identity: str  # the input identity of the search index; "" without an active version


def dictionary_identity(version: str, digest: str) -> str:
    """The dictionary part of the search index's input identity: number and content digest."""

    return f"{version}:{digest}"


def identity_digest(identity: str) -> str:
    return identity.rpartition(":")[2]


def version_identity(version: DictionaryVersion | None) -> str:
    return "" if version is None else dictionary_identity(version.version, version.content_digest)


async def read_dictionary(session: AsyncSession, tenant_id: int) -> DictionaryRead:
    repository = DictionaryRepository(session)
    active = await repository.version(tenant_id, DictionaryStatus.ACTIVE)
    if active is None:
        return DictionaryRead(empty_dictionary(), "")
    objects = await repository.objects(active)
    columns = await repository.columns(active)
    actual = records_digest(objects, columns)
    if actual != active.content_digest:
        log_event(
            logger,
            "dictionary.integrity_mismatch",
            stored_digest=active.content_digest,
            actual_digest=actual,
        )
    dictionary = load_dictionary(objects, columns, active.version, active.content_digest)
    return DictionaryRead(dictionary, version_identity(active))
