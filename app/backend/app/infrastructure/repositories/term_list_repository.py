"""Persistence of term lists and their terms (data-dictionary 005-list-search Veri ve geçiş).

Every query is scoped to a tenant except the process-wide checks of running lists. A list and its
terms are written in one transaction; an older list of the same owner beyond the newest five is
deleted physically in the transaction that writes the new one, its terms with it.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.tenant import Tenant
from app.domain.models.term_list import TermList, TermListItem
from app.domain.models.user import User
from app.domain.term_lists import KEPT_PER_OWNER, ListStatus


@dataclass(frozen=True, slots=True)
class ListRow:
    """A list with its owner and tenant as the endpoints and the runner need them."""

    record: TermList
    owner_public_id: str
    owner_display_name: str
    tenant_public_id: str


@dataclass(frozen=True, slots=True)
class ListSummaryRow:
    record: TermList
    owner_public_id: str
    owner_display_name: str
    done: int


_DONE = or_(TermListItem.answer.is_not(None), TermListItem.error_code.is_not(None))


def _with_owner() -> Any:
    return (
        select(TermList, User.public_id, User.display_name, Tenant.public_id)
        .join(User, User.user_id == TermList.owner_id)
        .join(Tenant, Tenant.tenant_id == TermList.tenant_id)
    )


class TermListRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ reading

    async def running(self, tenant_id: int) -> ListRow | None:
        statement = _with_owner().where(
            TermList.tenant_id == tenant_id, TermList.status == ListStatus.RUNNING.value
        )
        row = (await self.session.execute(statement)).first()
        return ListRow(*row) if row is not None else None

    async def find(self, tenant_id: int, public_id: str) -> ListRow | None:
        statement = _with_owner().where(
            TermList.tenant_id == tenant_id, TermList.public_id == public_id
        )
        row = (await self.session.execute(statement)).first()
        return ListRow(*row) if row is not None else None

    async def find_by_id(self, term_list_id: int) -> ListRow | None:
        statement = _with_owner().where(TermList.term_list_id == term_list_id)
        row = (await self.session.execute(statement)).first()
        return ListRow(*row) if row is not None else None

    async def items(self, term_list_id: int) -> list[TermListItem]:
        statement = (
            select(TermListItem)
            .where(TermListItem.term_list_id == term_list_id)
            .order_by(TermListItem.position)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def item(self, term_list_id: int, position: int) -> TermListItem | None:
        return await self.session.get(TermListItem, (term_list_id, position))

    async def next_unanswered(self, term_list_id: int, after: int) -> TermListItem | None:
        """The first term after ``after`` without an answer (an earlier error included)."""

        statement = (
            select(TermListItem)
            .where(
                TermListItem.term_list_id == term_list_id,
                TermListItem.position > after,
                TermListItem.answer.is_(None),
            )
            .order_by(TermListItem.position)
            .limit(1)
        )
        return (await self.session.execute(statement)).scalars().first()

    async def unanswered_count(self, term_list_id: int) -> int:
        statement = select(func.count()).where(
            TermListItem.term_list_id == term_list_id, TermListItem.answer.is_(None)
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def page(
        self, tenant_id: int, owner_id: int, page: int, page_size: int
    ) -> tuple[list[ListSummaryRow], int]:
        """The owner's lists, newest first (same upload time: newest id first)."""

        done = (
            select(func.count())
            .where(TermListItem.term_list_id == TermList.term_list_id, _DONE)
            .scalar_subquery()
        )
        where = and_(TermList.tenant_id == tenant_id, TermList.owner_id == owner_id)
        statement = (
            select(TermList, User.public_id, User.display_name, done)
            .join(User, User.user_id == TermList.owner_id)
            .where(where)
            .order_by(TermList.created_at.desc(), TermList.term_list_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = [ListSummaryRow(*row) for row in (await self.session.execute(statement)).all()]
        total = int(
            (
                await self.session.execute(select(func.count()).select_from(TermList).where(where))
            ).scalar_one()
        )
        return rows, total

    # ------------------------------------------------------------------ writing

    async def add(self, record: TermList, terms: list[str]) -> None:
        """The list, its terms in file order and the owner's newest five only."""

        self.session.add(record)
        await self.session.flush()
        self.session.add_all(
            TermListItem(
                term_list_id=record.term_list_id,
                position=position,
                term=term,
                created_by=record.owner_id,
                updated_by=record.owner_id,
            )
            for position, term in enumerate(terms, 1)
        )
        await self.session.flush()
        keep = (
            select(TermList.term_list_id)
            .where(TermList.tenant_id == record.tenant_id, TermList.owner_id == record.owner_id)
            .order_by(TermList.created_at.desc(), TermList.term_list_id.desc())
            .limit(KEPT_PER_OWNER)
        )
        old = select(TermList.term_list_id).where(
            TermList.tenant_id == record.tenant_id,
            TermList.owner_id == record.owner_id,
            TermList.term_list_id.not_in(keep),
        )
        stale = list((await self.session.execute(old)).scalars().all())
        if stale:
            await self.session.execute(
                delete(TermListItem).where(TermListItem.term_list_id.in_(stale))
            )
            await self.session.execute(delete(TermList).where(TermList.term_list_id.in_(stale)))

    async def set_list(self, term_list_id: int, **values: Any) -> None:
        await self.session.execute(
            update(TermList).where(TermList.term_list_id == term_list_id).values(**values)
        )

    async def set_item(self, term_list_id: int, position: int, **values: Any) -> None:
        await self.session.execute(
            update(TermListItem)
            .where(TermListItem.term_list_id == term_list_id, TermListItem.position == position)
            .values(**values)
        )

    async def running_lists(self, started_before: datetime | None = None) -> list[TermList]:
        """Every list of every tenant marked running (optionally only slices begun before)."""

        statement = select(TermList).where(TermList.status == ListStatus.RUNNING.value)
        if started_before is not None:
            statement = statement.where(TermList.run_started_at < started_before)
        return list((await self.session.execute(statement)).scalars().all())
