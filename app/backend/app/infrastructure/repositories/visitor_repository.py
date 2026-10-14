"""Persistence of visitors (application-foundation 003-anonymous-visitor Requirement 4)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.mixins import new_public_id
from app.domain.models.visitor import Visitor


@dataclass(frozen=True, slots=True)
class VisitorRow:
    visitor_id: int
    public_id: str


class VisitorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists(self, device_key: str) -> bool:
        found = await self.session.scalar(
            select(Visitor.visitor_id).where(Visitor.device_key == device_key)
        )
        return found is not None

    async def seen(
        self,
        *,
        tenant_id: int,
        device_key: str,
        address: str,
        host: str | None,
        at: datetime,
    ) -> VisitorRow:
        """Open the visitor of ``device_key`` or record its latest request; one row per key even
        when first requests arrive together."""

        statement = (
            insert(Visitor)
            .values(
                public_id=new_public_id(),
                tenant_id=tenant_id,
                device_key=device_key,
                first_seen_at=at,
                last_seen_at=at,
                last_address=address,
                last_host=host,
            )
            .on_conflict_do_update(
                index_elements=[Visitor.device_key],
                set_={
                    "last_seen_at": at,
                    "last_address": address,
                    "last_host": host,
                    "updated_at": func.now(),
                },
            )
            .returning(Visitor.visitor_id, Visitor.public_id)
        )
        row = (await self.session.execute(statement)).one()
        return VisitorRow(int(row[0]), str(row[1]))
