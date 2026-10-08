"""The word lists' single read function for the engine (vocabulary-management Requirement 2).

Term groups come in list order as ``TermGroup(term, equivalents, domain, note)`` by the source's
``load_term_dictionary`` rule (texts trimmed, empty terms and equivalents dropped); stopwords as
the set the engine's ``load_stopwords`` makes of them (folded and stemmed forms). With the seed
lists this is the source's 45 groups and 124 forms. Each list's identity is its stored content
digest.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.analysis import TermGroup
from app.domain.vocabulary import VocabularyList
from app.infrastructure.repositories.vocabulary_repository import VocabularyRepository
from app.services.analysis.text.normalize import load_stopwords


@dataclass(frozen=True, slots=True)
class WordLists:
    term_groups: tuple[TermGroup, ...]
    stopwords: frozenset[str]
    terms_digest: str
    stopwords_digest: str


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def term_groups(items: Iterable[Mapping[str, Any]]) -> list[TermGroup]:
    groups: list[TermGroup] = []
    for item in items:
        term = _text(item.get("term"))
        if not term:
            continue
        raw = item.get("equivalents")
        equivalents = tuple(e for e in map(_text, raw if isinstance(raw, list) else []) if e)
        groups.append(
            TermGroup(term, equivalents, _text(item.get("domain")), _text(item.get("note")))
        )
    return groups


def stopword_forms(items: Iterable[Mapping[str, Any]]) -> frozenset[str]:
    return load_stopwords(_text(item.get("word")) for item in items)


async def read_word_lists(session: AsyncSession, tenant_id: int) -> WordLists:
    repository = VocabularyRepository(session)
    terms_header = await repository.header(tenant_id, VocabularyList.TERMS)
    stopwords_header = await repository.header(tenant_id, VocabularyList.STOPWORDS)
    terms = await repository.items(tenant_id, VocabularyList.TERMS)
    stopwords = await repository.items(tenant_id, VocabularyList.STOPWORDS)
    return WordLists(
        term_groups=tuple(term_groups(terms)),
        stopwords=stopword_forms(stopwords),
        terms_digest=terms_header.content_digest if terms_header else "",
        stopwords_digest=stopwords_header.content_digest if stopwords_header else "",
    )
