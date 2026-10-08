"""The search index's inputs and their identity (search-settings Requirement 9).

The engine is built from four inputs: the active dictionary (dictionary-management), the term and
stopword lists (vocabulary-management) and the effective settings (this capability). A build
reads them all from one consistent database snapshot (``REPEATABLE READ``). Their identity is the
dictionary's number and content digest, the two lists' content digests and the digest of the
effective settings; it tells whether the serving engine still matches the database.
"""

import dataclasses
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.analysis import Dictionary, TermGroup
from app.domain.dictionary import DictionaryStatus
from app.domain.models.tenant import PLATFORM_TENANT_CODE, Tenant
from app.domain.vocabulary import VocabularyList
from app.infrastructure.repositories.dictionary_repository import DictionaryRepository
from app.infrastructure.repositories.search_setting_repository import (
    SearchSettingRepository,
)
from app.infrastructure.repositories.vocabulary_repository import VocabularyRepository
from app.services.dictionary_reading import read_dictionary, version_identity
from app.services.search_settings_schema import (
    check_value,
    effective_values,
    settings_digest,
)
from app.services.vocabulary_reading import read_word_lists

INPUT_NAMES = ("dictionary", "terms", "stopwords", "settings")


@dataclass(frozen=True, slots=True)
class InputIdentity:
    dictionary: str
    terms: str
    stopwords: str
    settings: str

    def differences(self, other: "InputIdentity") -> list[str]:
        return [name for name in INPUT_NAMES if getattr(self, name) != getattr(other, name)]


@dataclass(frozen=True, slots=True)
class SearchInputs:
    identity: InputIdentity
    dictionary: Dictionary
    term_groups: tuple[TermGroup, ...]
    stopwords: frozenset[str]
    settings_values: dict[str, Any]

    def replace(self, **changes: Any) -> "SearchInputs":
        identity_changes = {
            name: changes.pop(f"{name}_identity")
            for name in INPUT_NAMES
            if f"{name}_identity" in changes
        }
        return dataclasses.replace(
            self,
            identity=dataclasses.replace(self.identity, **identity_changes),
            **changes,
        )


async def platform_tenant_id(session: AsyncSession) -> int:
    tenant_id = await session.scalar(
        select(Tenant.tenant_id).where(
            Tenant.code == PLATFORM_TENANT_CODE, Tenant.is_deleted.is_(False)
        )
    )
    if tenant_id is None:
        raise LookupError("the platform tenant does not exist")
    return int(tenant_id)


def checked_settings(stored: dict[str, Any]) -> dict[str, Any]:
    """Effective values of stored ones; a stored value off the schema stops the build."""

    return effective_values({key: check_value(key, value) for key, value in stored.items()})


async def read_inputs(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: int
) -> SearchInputs:
    async with session_factory() as session:
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        dictionary = await read_dictionary(session, tenant_id)
        lists = await read_word_lists(session, tenant_id)
        stored = await SearchSettingRepository(session).stored(tenant_id)
    values = checked_settings(stored)
    return SearchInputs(
        identity=InputIdentity(
            dictionary=dictionary.identity,
            terms=lists.terms_digest,
            stopwords=lists.stopwords_digest,
            settings=settings_digest(values),
        ),
        dictionary=dictionary.dictionary,
        term_groups=lists.term_groups,
        stopwords=lists.stopwords,
        settings_values=values,
    )


async def read_identity(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: int
) -> InputIdentity:
    """The identity the database holds now, without reading the records."""

    async with session_factory() as session:
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        active = await DictionaryRepository(session).version(tenant_id, DictionaryStatus.ACTIVE)
        vocabulary = VocabularyRepository(session)
        terms = await vocabulary.header(tenant_id, VocabularyList.TERMS)
        stopwords = await vocabulary.header(tenant_id, VocabularyList.STOPWORDS)
        stored = await SearchSettingRepository(session).stored(tenant_id)
    try:
        values = checked_settings(stored)
    except ValueError:  # a value off the schema still has an identity: the stored one
        values = effective_values(stored)
    return InputIdentity(
        dictionary=version_identity(active),
        terms=terms.content_digest if terms else "",
        stopwords=stopwords.content_digest if stopwords else "",
        settings=settings_digest(values),
    )
