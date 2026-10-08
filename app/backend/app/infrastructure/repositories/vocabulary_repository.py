"""Persistence of the term dictionary and the stopwords (data-dictionary 002).

Reads return the current (non-deleted) items in list order. A replacement soft-deletes every
current item row of the list, inserts the new rows and updates the header in the caller's
transaction (Requirement 5).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.vocabulary import (
    VocabularyListHeader,
    VocabularyStopword,
    VocabularyTerm,
)
from app.domain.turkish_text import fold
from app.domain.vocabulary import VocabularyList


class VocabularyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def header(
        self, tenant_id: int, kind: VocabularyList, *, for_update: bool = False
    ) -> VocabularyListHeader | None:
        statement = select(VocabularyListHeader).where(
            VocabularyListHeader.tenant_id == tenant_id,
            VocabularyListHeader.public_id == kind.value,
            VocabularyListHeader.is_deleted.is_(False),
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def items(self, tenant_id: int, kind: VocabularyList) -> list[dict[str, Any]]:
        if kind is VocabularyList.TERMS:
            term_rows = await self.session.execute(
                select(
                    VocabularyTerm.term,
                    VocabularyTerm.equivalents,
                    VocabularyTerm.domain,
                    VocabularyTerm.note,
                )
                .where(
                    VocabularyTerm.tenant_id == tenant_id,
                    VocabularyTerm.is_deleted.is_(False),
                )
                .order_by(VocabularyTerm.position)
            )
            return [
                {
                    "term": term,
                    "equivalents": list(equivalents),
                    "domain": domain,
                    "note": note,
                }
                for term, equivalents, domain, note in term_rows.all()
            ]
        word_rows = await self.session.execute(
            select(VocabularyStopword.word, VocabularyStopword.group_name)
            .where(
                VocabularyStopword.tenant_id == tenant_id,
                VocabularyStopword.is_deleted.is_(False),
            )
            .order_by(VocabularyStopword.position)
        )
        return [{"word": word, "group": group} for word, group in word_rows.all()]

    async def replace(
        self,
        header: VocabularyListHeader,
        items: Sequence[dict[str, Any]],
        *,
        digest: str,
        source: str,
        user_id: int | None,
        now: datetime,
    ) -> int:
        """Replace the list's items and raise its revision; returns the new revision."""

        model: type[VocabularyTerm | VocabularyStopword]
        kind = VocabularyList(header.public_id)
        model = VocabularyTerm if kind is VocabularyList.TERMS else VocabularyStopword
        await self.session.execute(
            update(model)
            .where(model.tenant_id == header.tenant_id, model.is_deleted.is_(False))
            .values(is_deleted=True, deleted_at=now, deleted_by=user_id, updated_at=now)
        )
        common = {
            "tenant_id": header.tenant_id,
            "vocabulary_list_id": header.vocabulary_list_id,
            "created_at": now,
            "updated_at": now,
            "created_by": user_id,
            "updated_by": user_id,
        }
        if kind is VocabularyList.TERMS:
            rows = [
                {
                    **common,
                    "position": position,
                    "term": item["term"],
                    "term_key": fold(item["term"]),
                    "equivalents": list(item["equivalents"]),
                    "domain": item["domain"],
                    "note": item["note"],
                }
                for position, item in enumerate(items)
            ]
        else:
            rows = [
                {
                    **common,
                    "position": position,
                    "word": item["word"],
                    "word_key": fold(item["word"]),
                    "group_name": item["group"],
                }
                for position, item in enumerate(items)
            ]
        if rows:
            await self.session.execute(insert(model), rows)
        revision = header.revision + 1
        await self.session.execute(
            update(VocabularyListHeader)
            .where(VocabularyListHeader.vocabulary_list_id == header.vocabulary_list_id)
            .values(
                revision=revision,
                content_digest=digest,
                last_source=source,
                updated_at=now,
                updated_by=user_id,
            )
        )
        return revision
