"""The visitor of a main-screen request (application-foundation 003-anonymous-visitor
Requirement 3, Decision 1-4).

Main-screen endpoints take no session: the identity is the device id in ``X-Device-Id``. A tenant
header, when the client sends one, must name the platform tenant. The visitor is opened or
refreshed and committed before the endpoint runs, so the endpoint's own work starts clean.
"""

from typing import Annotated

from fastapi import Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_address import resolve_client_address
from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError
from app.db.session import get_db
from app.services.analysis.jobs import Asker
from app.services.visitors import (
    DEVICE_HEADER,
    VisitorIdentity,
    checked_device_id,
    identify,
)


async def get_current_visitor(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    device_id: Annotated[
        str | None,
        Header(
            alias=DEVICE_HEADER,
            description="The browser's random device id (UUID 4) that identifies the visitor.",
        ),
    ] = None,
) -> VisitorIdentity:
    checked = checked_device_id(device_id)
    address = resolve_client_address(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        settings.trusted_proxy_networks,
    )
    identity = await identify(session, checked, address)
    requested_tenant = request.headers.get(settings.tenant_header)
    if requested_tenant is not None and requested_tenant.strip() != identity.tenant_public_id:
        raise ApplicationError(
            status.HTTP_403_FORBIDDEN,
            "tenant_forbidden",
            "Bu kiracıya erişim yetkiniz yok.",
        )
    await session.commit()
    return identity


CurrentVisitor = Annotated[VisitorIdentity, Depends(get_current_visitor)]


def visitor_asker(visitor: VisitorIdentity) -> Asker:
    """The visitor as the owner of what it starts, with its address and host name now."""

    label = " · ".join(part for part in (visitor.host, visitor.address) if part)
    return Asker(
        user_id=None,
        public_id=visitor.public_id,
        display_name=label,
        visitor_id=visitor.visitor_id,
        address=visitor.address,
        host=visitor.host,
    )
