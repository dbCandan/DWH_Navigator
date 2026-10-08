"""Persistence of model server connections (data-dictionary 003-llm-connection).

Reads exclude soft-deleted rows. Unique-index violations become the two domain conflicts of
Requirement 2 and 4, so services never inspect driver errors.
"""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.llm_integration import LlmIntegration
from app.domain.models.tenant import Tenant

_NAME_INDEX = "uq_llm_integration_tenant_name_key"
_ACTIVE_INDEX = "uq_llm_integration_tenant_active"


class IntegrationNameTaken(Exception):
    """Another non-deleted integration of the tenant has the same folded name."""


class ChatRoleTaken(Exception):
    """Another non-deleted integration of the tenant is already the active chat model."""


def _violated_index(error: IntegrityError) -> str | None:
    current: BaseException | None = error.orig
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = getattr(current, "constraint_name", None)
        if isinstance(name, str):
            return name
        current = current.__cause__ or current.__context__
    return None


class LlmIntegrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_tenant(self, tenant_id: int) -> None:
        """Serialize creations in the tenant, so the 50-integration limit holds."""

        await self.session.execute(
            select(Tenant.tenant_id).where(Tenant.tenant_id == tenant_id).with_for_update()
        )

    async def list_live(self, tenant_id: int) -> list[LlmIntegration]:
        """Non-deleted integrations in creation order."""

        rows = await self.session.scalars(
            select(LlmIntegration)
            .where(LlmIntegration.tenant_id == tenant_id, LlmIntegration.is_deleted.is_(False))
            .order_by(LlmIntegration.llm_integration_id)
        )
        return list(rows)

    async def count_live(self, tenant_id: int) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(LlmIntegration)
            .where(LlmIntegration.tenant_id == tenant_id, LlmIntegration.is_deleted.is_(False))
        )
        return int(total or 0)

    async def get_live(self, tenant_id: int, public_id: str) -> LlmIntegration | None:
        rows = await self.session.scalars(
            select(LlmIntegration).where(
                LlmIntegration.tenant_id == tenant_id,
                LlmIntegration.public_id == public_id,
                LlmIntegration.is_deleted.is_(False),
            )
        )
        return rows.first()

    async def active(self, tenant_id: int) -> LlmIntegration | None:
        rows = await self.session.scalars(
            select(LlmIntegration).where(
                LlmIntegration.tenant_id == tenant_id,
                LlmIntegration.active.is_(True),
                LlmIntegration.is_deleted.is_(False),
            )
        )
        return rows.first()

    async def name_key_taken(self, tenant_id: int, name_key: str, *, except_id: int | None) -> bool:
        query = select(LlmIntegration.llm_integration_id).where(
            LlmIntegration.tenant_id == tenant_id,
            LlmIntegration.name_key == name_key,
            LlmIntegration.is_deleted.is_(False),
        )
        if except_id is not None:
            query = query.where(LlmIntegration.llm_integration_id != except_id)
        return (await self.session.scalar(query.limit(1))) is not None

    async def other_active(self, tenant_id: int, except_id: int | None) -> list[LlmIntegration]:
        query = select(LlmIntegration).where(
            LlmIntegration.tenant_id == tenant_id,
            LlmIntegration.active.is_(True),
            LlmIntegration.is_deleted.is_(False),
        )
        if except_id is not None:
            query = query.where(LlmIntegration.llm_integration_id != except_id)
        return list(await self.session.scalars(query))

    async def flush(self) -> None:
        """Write pending changes inside a savepoint; a unique conflict leaves the session usable."""

        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as error:
            index = _violated_index(error)
            if index == _NAME_INDEX:
                raise IntegrationNameTaken() from None
            if index == _ACTIVE_INDEX:
                raise ChatRoleTaken() from None
            raise

    async def record_test(
        self, integration_id: int, *, at: datetime, ok: bool, summary: str
    ) -> None:
        """Store a test result without counting it as a connection change (Requirement 15)."""

        await self.session.execute(
            update(LlmIntegration)
            .where(LlmIntegration.llm_integration_id == integration_id)
            .values(
                last_test_at=at,
                last_test_ok=ok,
                last_test_summary=summary,
                updated_at=LlmIntegration.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
