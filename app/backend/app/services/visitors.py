"""Who a main-screen request comes from (application-foundation 003-anonymous-visitor).

A visitor is known by the random device id its browser sends (Decision 1); only its SHA-256 is
stored. The client address comes from the trusted-ingress rule and the host name from a reverse
DNS lookup of it (Decision 2), cached so a request rarely waits for DNS. New visitors are limited
per address (Requirement 6). Neither the device id, the address nor the host name is logged.
"""

import asyncio
import hashlib
import logging
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.rate_window import SlidingWindow
from app.domain.models.tenant import PLATFORM_TENANT_CODE
from app.domain.models.visitor import HOST_MAX_CHARS
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.repositories.visitor_repository import VisitorRepository

logger = logging.getLogger("app.visitor")

DEVICE_HEADER = "X-Device-Id"
WINDOW_SECONDS = 60
NEW_VISITOR_LIMIT = 20
HOST_LOOKUP_SECONDS = 1.0
HOST_CACHE_SECONDS = 3600.0
_HOST_CACHE_MAX = 10_000

_new_visitors = SlidingWindow(limit=NEW_VISITOR_LIMIT, window_seconds=WINDOW_SECONDS)
_hosts: dict[str, tuple[float, str | None]] = {}


@dataclass(frozen=True, slots=True)
class VisitorIdentity:
    """The visitor of a request, in the platform tenant, with its address and host name now."""

    tenant_id: int
    tenant_public_id: str
    visitor_id: int
    public_id: str
    address: str
    host: str | None


def device_id_required() -> ApplicationError:
    return ApplicationError(
        status.HTTP_400_BAD_REQUEST,
        "device_id_required",
        "Tarayıcı kimliği eksik; sayfayı yenileyin.",
    )


def rate_limited() -> ApplicationError:
    return ApplicationError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "rate_limited",
        "Çok sık istek gönderildi; bir dakika sonra yeniden deneyin.",
        headers={"Retry-After": str(WINDOW_SECONDS)},
    )


def checked_device_id(raw: str | None) -> str:
    """The canonical text of a UUID version 4; anything else is refused."""

    try:
        parsed = UUID((raw or "").strip())
    except ValueError:
        raise device_id_required() from None
    if parsed.version != 4:
        raise device_id_required()
    return str(parsed)


def device_key(device_id: str) -> str:
    return hashlib.sha256(device_id.encode("ascii")).hexdigest()


def _system_lookup(address: str) -> str | None:
    try:
        return socket.gethostbyaddr(address)[0]
    except (OSError, UnicodeError):
        return None


HostLookup = Callable[[str], Awaitable[str | None]]


async def _threaded_lookup(address: str) -> str | None:
    return await asyncio.to_thread(_system_lookup, address)


_lookup: HostLookup = _threaded_lookup


def use_host_lookup(lookup: HostLookup | None) -> None:
    """Replace the reverse DNS lookup (tests); None restores the system resolver."""

    global _lookup
    _lookup = lookup or _threaded_lookup
    _hosts.clear()


def reset_limits() -> None:
    _new_visitors.clear()
    _hosts.clear()


async def host_of(address: str) -> str | None:
    """The host name of ``address`` from reverse DNS, cached; None when there is none in time."""

    now = time.monotonic()
    cached = _hosts.get(address)
    if cached is not None and now - cached[0] < HOST_CACHE_SECONDS:
        return cached[1]
    try:
        host = await asyncio.wait_for(_lookup(address), HOST_LOOKUP_SECONDS)
    except TimeoutError:
        host = None
    host = host.rstrip(".")[:HOST_MAX_CHARS] if host else None
    _hosts.pop(address, None)
    _hosts[address] = (now, host)
    while len(_hosts) > _HOST_CACHE_MAX:
        del _hosts[next(iter(_hosts))]
    return host


async def identify(session: AsyncSession, device_id: str, address: str) -> VisitorIdentity:
    """The visitor of ``device_id``, opened on its first request (Requirement 4)."""

    tenant = await UserRepository(session).get_tenant_by_code(PLATFORM_TENANT_CODE)
    if tenant is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "tenant_not_found", "Kiracı bulunamadı.")
    key = device_key(device_id)
    repository = VisitorRepository(session)
    is_new = not await repository.exists(key)
    if is_new and not _new_visitors.hit(address):
        raise rate_limited()
    host = await host_of(address)
    row = await repository.seen(
        tenant_id=tenant.tenant_id,
        device_key=key,
        address=address,
        host=host,
        at=datetime.now(UTC),
    )
    if is_new:
        log_event(logger, "visitor.created", visitor_id=row.public_id)
    return VisitorIdentity(
        tenant_id=tenant.tenant_id,
        tenant_public_id=tenant.public_id,
        visitor_id=row.visitor_id,
        public_id=row.public_id,
        address=address,
        host=host,
    )
