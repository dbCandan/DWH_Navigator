"""A real-TCP fake OpenAI-compatible model server (data-dictionary 003-llm-connection tests).

It speaks just enough HTTP/1.1, plain or over TLS with its own test certificate authority. Every
request is recorded byte for byte (method, path, headers, body) and answered by the scenario the
test installs. Each answer closes the connection. The certificate authority and server key are
generated per test run and written only to the pytest temporary directory. ``close`` drops every
connection still open, so a client that keeps one idle cannot hold the server open.
"""

import asyncio
import datetime as dt
import ipaddress
import json
import ssl
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

HOST_NAME = "llm.test.internal"


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


Writer = asyncio.StreamWriter
Scenario = Callable[[RecordedRequest, asyncio.StreamReader, Writer], Awaitable[None]]


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


@dataclass
class ServerPki:
    ca_path: Path
    certificate_path: Path
    key_path: Path


def write_pki(directory: Path) -> ServerPki:
    """A fresh certificate authority and a server certificate for HOST_NAME and 127.0.0.1."""

    ca_key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.UTC)
    ca = (
        x509.CertificateBuilder()
        .subject_name(_name("Deneme Kök CA"))
        .issuer_name(_name("Deneme Kök CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    server_key = ec.generate_private_key(ec.SECP256R1())
    server = (
        x509.CertificateBuilder()
        .subject_name(_name(HOST_NAME))
        .issuer_name(ca.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(HOST_NAME), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([x509.OID_SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    directory.mkdir(parents=True, exist_ok=True)
    pki = ServerPki(directory / "ca.pem", directory / "server.pem", directory / "server.key")
    pki.ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    pki.certificate_path.write_bytes(server.public_bytes(serialization.Encoding.PEM))
    pki.key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return pki


_REASONS = {200: "OK", 307: "Temporary Redirect", 400: "Bad Request", 500: "Server Error"}


def http_response(
    status: int, body: bytes, *, content_type: str = "application/json", extra: str = ""
) -> bytes:
    head = (
        f"HTTP/1.1 {status} {_REASONS.get(status, 'Status')}\r\nContent-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n{extra}Connection: close\r\n\r\n"
    )
    return head.encode("ascii") + body


def json_response(payload: object, status: int = 200) -> bytes:
    return http_response(status, json.dumps(payload).encode("utf-8"))


def chat_reply(
    content: str,
    *,
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
    finish_reason: str | None = None,
) -> bytes:
    choice: dict[str, Any] = {"message": {"role": "assistant", "content": content}}
    if finish_reason is not None:
        choice["finish_reason"] = finish_reason
    return json_response(
        {
            "choices": [choice],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        }
    )


def models_reply(*model_ids: str) -> bytes:
    return json_response(
        {"object": "list", "data": [{"id": mid, "owned_by": "deneme"} for mid in model_ids]}
    )


def respond(payload: bytes) -> Scenario:
    async def scenario(
        request: RecordedRequest, reader: asyncio.StreamReader, writer: Writer
    ) -> None:
        writer.write(payload)
        await writer.drain()

    return scenario


def script(responses: Iterable[bytes], *, models: bytes | None = None) -> Scenario:
    """Chat requests get ``responses`` in order; ``GET .../models`` gets ``models``."""

    pending = list(responses)

    async def scenario(
        request: RecordedRequest, reader: asyncio.StreamReader, writer: Writer
    ) -> None:
        if request.method == "GET":
            writer.write(models if models is not None else models_reply("deneme-model"))
        else:
            writer.write(pending.pop(0))
        await writer.drain()

    return scenario


def hang(started: asyncio.Event | None = None) -> Scenario:
    """Never answer; return when the client closes the connection."""

    async def scenario(
        request: RecordedRequest, reader: asyncio.StreamReader, writer: Writer
    ) -> None:
        if started is not None:
            started.set()
        while await reader.read(1024):
            pass

    return scenario


@dataclass
class FakeLlmServer:
    pki: ServerPki | None = None
    scenario: Scenario | None = None
    requests: list[RecordedRequest] = field(default_factory=list)
    connections: int = 0
    active: int = 0
    peak: int = 0
    # monotonic time at which a connection that had sent a request was closed by the client
    closed_at: list[float] = field(default_factory=list)
    port: int = 0
    _server: asyncio.Server | None = None
    _writers: set[Writer] = field(default_factory=set)

    async def start(self, *, certificate: ServerPki | None = None) -> "FakeLlmServer":
        context: ssl.SSLContext | None = None
        pki = certificate or self.pki
        if pki is not None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(pki.certificate_path, pki.key_path)
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0, ssl=context)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            # Since Python 3.12 wait_closed also waits for open connections; an idle keep-alive
            # connection or an unanswered request would otherwise keep it waiting forever.
            for writer in list(self._writers):
                writer.transport.abort()
            await self._server.wait_closed()

    def url(self, path: str = "/v1", *, host: str | None = None) -> str:
        scheme = "https" if self.pki is not None else "http"
        name = host or (HOST_NAME if self.pki is not None else "127.0.0.1")
        return f"{scheme}://{name}:{self.port}{path}"

    def chat_bodies(self) -> list[bytes]:
        return [r.body for r in self.requests if r.path.endswith("/chat/completions")]

    async def _handle(self, reader: asyncio.StreamReader, writer: Writer) -> None:
        self.connections += 1
        self._writers.add(writer)
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            method, path, _ = request_line.decode("latin-1").split(" ", 2)
            headers: dict[str, str] = {}
            while True:
                line = (await reader.readline()).decode("latin-1").rstrip("\r\n")
                if not line:
                    break
                name, _, value = line.partition(":")
                headers[name.strip().lower()] = value.strip()
            body = await reader.readexactly(int(headers.get("content-length", "0")))
            request = RecordedRequest(method, path, headers, body)
            self.requests.append(request)
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                assert self.scenario is not None
                await self.scenario(request, reader, writer)
            finally:
                self.active -= 1
                self.closed_at.append(time.monotonic())
        except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, ssl.SSLError):
                pass
