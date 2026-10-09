"""Request policy of the web server: who may use the admin screen, which requests may
change something, and the headers every response carries. Pure apart from reading the
environment once (``AdminGuard.from_env``); the server applies the decisions.

Admin screen (``/admin``, settings, model connections, analysis records): with a password
(``VSA_ADMIN_PASSWORD`` or a file named by ``VSA_ADMIN_PASSWORD_FILE``) it asks for it
(HTTP Basic, any user name); without one it opens only to a browser on this machine,
reached directly (not through a proxy) by a loopback address — so a container or a
server shared on the network never exposes it by accident.

State-changing requests (POST) must come from the app's own pages: a browser's
``Sec-Fetch-Site`` (or, from an older browser, ``Origin``) naming another site is refused
(CSRF).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import os
import re
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from vsa.text.normalize import fold

ADMIN_PREFIXES = ("/admin", "/api/admin/", "/api/settings", "/api/reindex", "/api/llm")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_FAILURES = 5  # wrong passwords from one address before it is locked out
LOCKOUT_SECONDS = 300.0
REALM = 'Basic realm="DWH Navigator yonetim", charset="UTF-8"'



class Headers(Protocol):
    """Request headers (``http.server``'s message or a plain dict)."""

    def get(self, name: str, /) -> str | None: ...


_SCRIPT = re.compile(rb"<script>(.*?)</script>", re.S)
_STYLE = re.compile(rb"<style>(.*?)</style>", re.S)

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Permitted-Cross-Domain-Policies": "none",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cache-Control": "no-store",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def is_admin_path(path: str) -> bool:
    return path == "/admin" or path.startswith(ADMIN_PREFIXES)


def _hashes(blocks: list[bytes]) -> str:
    return " ".join(
        f"'sha256-{base64.b64encode(hashlib.sha256(b).digest()).decode()}'" for b in blocks
    ) or "'none'"


def page_csp(html: bytes) -> str:
    """CSP of a page: only its own inline script and style blocks (by hash) apply — the
    pages set element styles through CSSOM, which CSP allows; it talks to this server only;
    no frames, no plugins, no external anything (closed network, ADR-031)."""
    return (
        f"default-src 'none'; script-src {_hashes(_SCRIPT.findall(html))}; "
        f"style-src {_hashes(_STYLE.findall(html))}; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _host_name(host_header: str) -> str:
    """``localhost:8765`` -> ``localhost``; ``[::1]:8765`` -> ``::1``."""
    return (urlparse(f"//{host_header}").hostname or "").rstrip(".")


def cross_site(headers: Headers) -> bool:
    """A state-changing request sent by another site's page (CSRF)."""
    site = fold((headers.get("Sec-Fetch-Site") or "").strip())
    if site:
        return site not in ("same-origin", "none")
    origin = (headers.get("Origin") or "").strip()
    if not origin or origin == "null":
        return bool(origin)  # "null": a sandboxed or file page — not ours
    host = headers.get("X-Forwarded-Host") or headers.get("Host") or ""
    return fold(urlparse(origin).netloc) != fold(host.split(",")[0].strip())


@dataclass(slots=True)
class Decision:
    allowed: bool
    status: int = 200  # 401 (ask for the password), 403, 429
    message: str = ""


@dataclass(slots=True)
class AdminGuard:
    password: str = ""
    _failures: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AdminGuard:
        env = os.environ if env is None else env
        password = env.get("VSA_ADMIN_PASSWORD", "")
        file = env.get("VSA_ADMIN_PASSWORD_FILE", "")
        if not password and file:
            password = Path(file).read_text(encoding="utf-8").strip()
        return cls(password)

    @property
    def protected(self) -> bool:
        return bool(self.password)

    def check(self, client_ip: str, headers: Headers) -> Decision:
        if not self.protected:
            local = (
                _is_loopback(client_ip)
                and not headers.get("X-Forwarded-For")
                and _host_name(headers.get("Host") or "") in LOOPBACK_HOSTS  # DNS rebinding
            )
            if local:
                return Decision(True)
            return Decision(False, 403, "Yönetim ekranı yalnız sunucunun kendisinden açılır. "
                            "Ağdan erişim için VSA_ADMIN_PASSWORD tanımlayın.")  # fmt: skip
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._failures.get(client_ip, []) if now - t < LOCKOUT_SECONDS]
            self._failures[client_ip] = recent
            if len(recent) >= MAX_FAILURES:
                return Decision(False, 429, "Çok sayıda hatalı deneme; sonra yeniden deneyin.")
        given = _basic_password(headers.get("Authorization") or "")
        if given is not None and hmac.compare_digest(
            given.encode("utf-8"), self.password.encode("utf-8")
        ):
            return Decision(True)
        if given is not None:
            with self._lock:
                self._failures.setdefault(client_ip, []).append(now)
        return Decision(False, 401, "Yönetim ekranı için parola gerekli.")


def _basic_password(header: str) -> str | None:
    scheme, _, value = header.partition(" ")
    if fold(scheme) != "basic" or not value:
        return None
    try:
        decoded = base64.b64decode(value.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return decoded.partition(":")[2]
