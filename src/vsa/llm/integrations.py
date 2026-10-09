"""LLM integrations (ADR-032): named connections to OpenAI-compatible servers.

Each integration is one server (base URL + key) and may fill the **chat** role (the
analyst). Only active integrations are used, and the role is held by at most one active
integration — activating a second holder is refused unless the caller asks to replace the
first.

When the integrations file exists it is authoritative: the ``llm`` settings get their
connection from the active integrations, and the chat role is off when nobody holds it.
Entries written before vector search was removed may still carry an embedding model; it
is ignored on load. Without the file
the ``llm:`` section of ``settings.yaml`` works as before (CLI, eval, older setups).

Pure: reading and writing the file is in ``config.py``, talking to servers in ``client.py``.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from vsa.text.normalize import fold

CHAT = "chat"
ROLE_LABEL = {CHAT: "Sohbet modeli"}
EFFORTS = ("none", "low", "medium", "high", "")
INTERNAL_SUFFIXES = (".local", ".lan", ".internal", ".intranet", ".corp", ".localhost")
_SHARED = ipaddress.ip_network("100.64.0.0/10")


@dataclass(slots=True)
class Integration:
    id: str
    name: str
    endpoint: str
    api_key: str = ""
    enabled: bool = False
    chat_model: str = ""
    temperature: float = 0.0
    timeout: int = 900  # the analyst's second step writes a long answer (ADR-029)
    reasoning_effort: str = "none"
    seed: int = 42  # -1 = don't send
    last_test: dict[str, Any] = field(default_factory=dict)  # at, ok, summary

    @property
    def roles(self) -> list[str]:
        return [CHAT] if self.chat_model else []

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def public(self) -> dict[str, Any]:
        """For the browser: the key never leaves the server, only whether there is one."""
        d = self.to_dict()
        d.pop("api_key")
        d["has_key"] = bool(self.api_key)
        d["roles"] = self.roles
        d["internal"] = is_internal(self.endpoint)
        return d


def from_dict(d: dict[str, Any]) -> Integration:
    """Unknown keys (an old file's retired fields) are dropped; an entry left without a
    chat model cannot be active."""
    known = set(Integration.__dataclass_fields__)
    item = Integration(**{k: v for k, v in d.items() if k in known})
    if not item.roles:
        item.enabled = False
    return item


def normalize_endpoint(url: str) -> str:
    """Trim, drop a trailing slash and a pasted ``/chat/completions`` or ``/models``."""
    url = url.strip().rstrip("/")
    for tail in ("/chat/completions", "/models"):
        if url.endswith(tail):
            url = url[: -len(tail)]
    return url


def validate(item: Integration, others: list[Integration]) -> list[str]:
    """Problems in Turkish; empty when the integration can be saved."""
    errors: list[str] = []
    if not item.name.strip():
        errors.append("Ad boş olamaz")
    elif any(fold(o.name.strip()) == fold(item.name.strip()) for o in others if o.id != item.id):
        errors.append(f"“{item.name}” adında bir entegrasyon zaten var")
    parsed = urlparse(item.endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        errors.append("API adresi http:// veya https:// ile başlayan tam bir adres olmalı "
                      "(ör. http://10.0.0.5:8000/v1)")  # fmt: skip
    if not 0 <= item.temperature <= 2:
        errors.append("Sıcaklık 0 ile 2 arasında olmalı")
    if not 5 <= item.timeout <= 3600:
        errors.append("Zaman aşımı 5 ile 3600 saniye arasında olmalı")
    if item.reasoning_effort not in EFFORTS:
        errors.append("Düşünme modu geçersiz")
    return errors


def new_id(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")[:32] or "llm"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def holder(items: list[Integration], role: str) -> Integration | None:
    """The active integration that serves ``role``."""
    return next((i for i in items if i.enabled and role in i.roles), None)


def conflicts(items: list[Integration], target: Integration) -> list[Integration]:
    """Other active integrations holding a role ``target`` would take."""
    wanted = set(target.roles)
    return [i for i in items if i.enabled and i.id != target.id and wanted & set(i.roles)]


def is_internal(endpoint: str) -> bool:
    """Does the address point inside the network? Loopback, private ranges, single-label
    names (intranet hosts) and the usual internal suffixes count; anything else may leave
    the network — the screen warns, it does not forbid (the user decides)."""
    host = urlparse(endpoint).hostname or ""  # already lower case
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host or host.endswith(INTERNAL_SUFFIXES)
    # 100.64.0.0/10: carrier-grade NAT space, used by VPN overlays such as Tailscale
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip in _SHARED


def apply(llm: Any, items: list[Integration]) -> None:
    """Point ``llm`` (``LLMSettings``) at the active integrations; a free role is off."""
    chat = holder(items, CHAT)
    llm.enabled = chat is not None
    llm.endpoint = chat.endpoint if chat else ""
    llm.model = chat.chat_model if chat else ""
    llm.api_key = chat.api_key if chat else ""
    if chat is not None:
        llm.temperature = chat.temperature
        llm.timeout = chat.timeout
        llm.reasoning_effort = chat.reasoning_effort
        llm.seed = chat.seed


def from_llm_settings(llm: Any) -> list[Integration]:
    """The ``llm:`` section of an existing setup as integrations — run once, when the
    integrations file is first created, so the screen starts from what already works."""
    endpoint = str(getattr(llm, "endpoint", "") or "")
    if not endpoint:
        return []
    return [Integration(
        id="mevcut", name="Mevcut bağlantı", endpoint=normalize_endpoint(endpoint),
        api_key=llm.api_key, enabled=bool(llm.enabled and llm.model),
        chat_model=llm.model if llm.enabled else "",
        temperature=float(llm.temperature), timeout=int(llm.timeout),
        reasoning_effort=str(llm.reasoning_effort), seed=int(llm.seed),
    )]  # fmt: skip
