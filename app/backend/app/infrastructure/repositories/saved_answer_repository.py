"""Persistence of saved answers (data-dictionary 004-question-analysis Requirement 13-15).

Rows are written, replaced and deleted physically (Decision 9). Every query is scoped to a tenant.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.saved_answer import SavedAnswer

MAX_ENTRIES = 2000  # newest answers kept (source answer_store.MAX_ENTRIES)


@dataclass(frozen=True, slots=True)
class SavedAnswerSummary:
    total: int
    usable: int
    newest_at: datetime | None


class SavedAnswerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def newest(
        self,
        tenant_id: int,
        fingerprint: str,
        *,
        since: datetime | None,
        text_key: str | None = None,
        meaning_key: str | None = None,
    ) -> SavedAnswer | None:
        """The newest row with this fingerprint and text key (or meaning key) since ``since``."""

        statement = select(SavedAnswer).where(
            SavedAnswer.tenant_id == tenant_id, SavedAnswer.fingerprint == fingerprint
        )
        if text_key is not None:
            statement = statement.where(SavedAnswer.text_key == text_key)
        if meaning_key is not None:
            statement = statement.where(SavedAnswer.meaning_key == meaning_key)
        if since is not None:
            statement = statement.where(SavedAnswer.answered_at >= since)
        statement = statement.order_by(
            SavedAnswer.answered_at.desc(), SavedAnswer.saved_answer_id.desc()
        ).limit(1)
        return (await self.session.execute(statement)).scalars().first()

    async def put(
        self,
        tenant_id: int,
        *,
        query_text: str,
        text_key: str,
        meaning_key: str,
        fingerprint: str,
        result: dict[str, Any],
        answered_at: datetime,
        analysis_public_id: str | None,
        user_id: int | None,
    ) -> None:
        """Write the answer; the same tenant, text key and fingerprint replace the older row.
        Only the newest 2000 rows stay."""

        values = {
            "query_text": query_text,
            "meaning_key": meaning_key,
            "result": result,
            "answered_at": answered_at,
            "analysis_public_id": analysis_public_id,
            "updated_by": user_id,
        }
        statement = insert(SavedAnswer).values(
            tenant_id=tenant_id,
            text_key=text_key,
            fingerprint=fingerprint,
            created_by=user_id,
            **values,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_saved_answer_tenant_text_fingerprint",
            set_={**values, "updated_at": func.now(), "created_by": user_id},
        )
        await self.session.execute(statement)
        keep = (
            select(SavedAnswer.saved_answer_id)
            .where(SavedAnswer.tenant_id == tenant_id)
            .order_by(SavedAnswer.answered_at.desc(), SavedAnswer.saved_answer_id.desc())
            .limit(MAX_ENTRIES)
        )
        await self.session.execute(
            delete(SavedAnswer).where(
                SavedAnswer.tenant_id == tenant_id, SavedAnswer.saved_answer_id.not_in(keep)
            )
        )

    async def forget(self, tenant_id: int, text_key: str, meaning_key: str) -> int:
        """Delete the rows of a question and of those meaning the same, whatever the
        fingerprint (answer-feedback's "cevaba 👎 çoğunluğu")."""

        match = SavedAnswer.text_key == text_key
        if meaning_key:
            match = or_(match, SavedAnswer.meaning_key == meaning_key)
        result = await self.session.execute(
            delete(SavedAnswer)
            .where(SavedAnswer.tenant_id == tenant_id, match)
            .returning(SavedAnswer.saved_answer_id)
        )
        return len(result.all())

    async def clear(self, tenant_id: int) -> int:
        result = await self.session.execute(
            delete(SavedAnswer)
            .where(SavedAnswer.tenant_id == tenant_id)
            .returning(SavedAnswer.saved_answer_id)
        )
        return len(result.all())

    async def keyed(self, tenant_id: int) -> list[tuple[str, str, datetime]]:
        """Every row's question, fingerprint and time: whether a row is usable depends on
        its own question (the term groups it matches), so it is decided per row."""
        rows = await self.session.execute(
            select(SavedAnswer.query_text, SavedAnswer.fingerprint, SavedAnswer.answered_at).where(
                SavedAnswer.tenant_id == tenant_id
            )
        )
        return [(q, f, at) for q, f, at in rows.all()]
