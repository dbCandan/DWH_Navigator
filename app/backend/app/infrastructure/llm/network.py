"""Private-network policy and verified TLS of model traffic (003-llm-connection Requirement 10).

Every address a host name resolves to, and the address a connection actually reaches, must be in
the private ranges. The check runs in the connection layer before TLS or any request byte, so a
denied request never sends its body. Name resolution, TCP connect and the TLS handshake together
take at most the connect timeout (Requirement 9). No switch, setting or API lifts the policy.
"""

import asyncio
import socket
import ssl
import time
import typing
from collections.abc import Awaitable, Callable, Iterable
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from typing import Any

import httpcore
import httpx

PRIVATE_NETWORKS = tuple(
    ip_network(network)
    for network in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "100.64.0.0/10",
        "::1/128",
        "fe80::/10",
        "fc00::/7",
    )
)

# (host, port) -> resolved IP address strings in resolver order.
Resolver = Callable[[str, int], Awaitable[list[str]]]


class NetworkPolicyDenied(Exception):
    """The address resolves to, or connected to, an address outside the private ranges."""


class HostUnresolved(Exception):
    """The host name has no address."""


def is_private_address(value: str) -> bool:
    """True for an address in the policy ranges; an IPv4 address inside IPv6 is checked as IPv4."""

    try:
        address: IPv4Address | IPv6Address = ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(
        address.version == network.version and address in network for network in PRIVATE_NETWORKS
    )


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses


def _literal_address(host: str) -> str | None:
    try:
        return str(ip_address(host.strip("[]")))
    except ValueError:
        return None


async def resolve_private(
    resolver: Resolver, host: str, port: int, *, timeout: float | None
) -> list[str]:
    """Resolve ``host`` and require every address to be private; return them in order."""

    literal = _literal_address(host)
    if literal is not None:
        if not is_private_address(literal):
            raise NetworkPolicyDenied()
        return [literal]
    try:
        async with asyncio.timeout(timeout):
            addresses = await resolver(host, port)
    except TimeoutError:
        raise httpcore.ConnectTimeout("name resolution timed out") from None
    except OSError:
        raise HostUnresolved() from None
    if not addresses:
        raise HostUnresolved()
    if not all(is_private_address(address) for address in addresses):
        raise NetworkPolicyDenied()
    return addresses


def _remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    left = deadline - time.monotonic()
    if left <= 0:
        raise httpcore.ConnectTimeout("connecting took too long")
    return left


class _DeadlineStream(httpcore.AsyncNetworkStream):
    """A connected stream whose TLS handshake gets only what is left of the connect timeout."""

    def __init__(self, inner: httpcore.AsyncNetworkStream, deadline: float | None) -> None:
        self._inner = inner
        self._deadline = deadline

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._inner.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._inner.write(buffer, timeout)

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        left = _remaining(self._deadline)
        limit = left if timeout is None else min(timeout, left) if left is not None else timeout
        return await self._inner.start_tls(ssl_context, server_hostname, limit)

    def get_extra_info(self, info: str) -> typing.Any:
        return self._inner.get_extra_info(info)


class PrivateNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve with the policy, connect to a checked address and verify the connected peer."""

    def __init__(
        self, resolver: Resolver, inner: httpcore.AsyncNetworkBackend | None = None
    ) -> None:
        self._resolver = resolver
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        deadline = None if timeout is None else time.monotonic() + timeout
        addresses = await resolve_private(self._resolver, host, port, timeout=_remaining(deadline))
        last_error: Exception | None = None
        for address in addresses:
            try:
                stream = await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=_remaining(deadline),
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last_error = error
                continue
            peer = stream.get_extra_info("server_addr")
            if not peer or not is_private_address(str(peer[0])):
                await stream.aclose()
                raise NetworkPolicyDenied()
            return _DeadlineStream(stream, deadline)
        assert last_error is not None
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise NetworkPolicyDenied()

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PolicyTransport(httpx.AsyncHTTPTransport):
    """httpx transport whose connections go only through PrivateNetworkBackend."""

    def __init__(
        self,
        *,
        ssl_context: ssl.SSLContext,
        network_backend: httpcore.AsyncNetworkBackend,
        max_connections: int = 1,
    ) -> None:
        super().__init__(verify=ssl_context, trust_env=False)
        # httpx 0.28 builds its pool without a network-backend hook; the replacement keeps the
        # same verified TLS context and routes every connection through the policy backend.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
            keepalive_expiry=5.0,
            http1=True,
            http2=False,
            network_backend=network_backend,
        )


def tls_context(ca_bundle: str) -> ssl.SSLContext:
    """Verified TLS: the configured bundle, otherwise the image's system trust store."""

    context = ssl.create_default_context(cafile=ca_bundle or None)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context
