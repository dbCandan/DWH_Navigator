"""LLM integrations page of the admin screen (ADR-032): list, save, test, inventory,
activate / deactivate. Integrations live in ``data/llm_integrations.yaml`` next to the
settings file; every change rewrites it and rebuilds the engine with the new connection.

The API key never goes back to the browser; a blank key on save keeps the stored one.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

from vsa.config import integrations_path, read_integrations, write_integrations
from vsa.llm.client import LLMError, OpenAICompatibleClient
from vsa.llm.integrations import (
    CHAT,
    ROLE_LABEL,
    Integration,
    conflicts,
    from_llm_settings,
    holder,
    new_id,
    normalize_endpoint,
    validate,
)
from vsa.pipeline import Engine

INVENTORY_TIMEOUT = 6.0  # per server; an unreachable one must not hold the page
TEST_CHAT_TIMEOUT = 180  # first request may load the model into memory
TEST_QUESTION = "Türkiye'nin başkenti neresidir?"
TEST_SCHEMA = {
    "type": "object",
    "properties": {"cevap": {"type": "string"}},
    "required": ["cevap"],
    "additionalProperties": False,
}


class Host(Protocol):
    engine: Engine
    settings_path: Path

    def reload(self) -> None: ...


class LLMAdmin:
    def __init__(self, host: Host) -> None:
        self.host = host

    @property
    def path(self) -> Path:
        return integrations_path(self.host.settings_path)

    def items(self) -> list[Integration]:
        saved = read_integrations(self.path)
        # No file yet: start from the connection settings.yaml already describes; it is
        # written on the first change, until then nothing about the running app changes.
        return saved if saved is not None else from_llm_settings(self.host.engine.settings.llm)

    def _store(self, items: list[Integration]) -> None:
        write_integrations(self.path, items)
        self.host.reload()

    def _find(self, items: list[Integration], iid: object) -> Integration:
        for i in items:
            if i.id == iid:
                return i
        raise KeyError(str(iid))

    # ------------------------------------------------------------------ read

    def state(self) -> dict[str, Any]:
        items = self.items()
        engine = self.host.engine
        h = holder(items, CHAT)
        roles = {CHAT: None if h is None else {"id": h.id, "name": h.name, "model": h.chat_model}}
        return {
            "items": [i.public() for i in items],
            "roles": roles,
            "saved": self.path.exists(),
            "path": str(self.path),
            "engine": {"chat_down": engine.llm.health() if engine.llm.available else ""},
        }

    # ------------------------------------------------------------------ change

    def save(self, body: dict[str, Any]) -> dict[str, Any]:
        items = self.items()
        iid = str(body.get("id") or "")
        old = self._find(items, iid) if iid else None
        try:
            item = Integration(
                id=iid or new_id(str(body.get("name", "")), {i.id for i in items}),
                name=str(body.get("name", "")).strip(),
                endpoint=normalize_endpoint(str(body.get("endpoint", ""))),
                api_key=str(body.get("api_key") or "") or (old.api_key if old else ""),
                enabled=old.enabled if old else False,
                chat_model=str(body.get("chat_model") or "").strip(),
                temperature=float(body.get("temperature", 0.0)),
                timeout=int(body.get("timeout", 900)),
                reasoning_effort=str(body.get("reasoning_effort", "none")),
                seed=int(body.get("seed", 42)),
                last_test=old.last_test if old else {},
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Sayısal alanlardan biri geçersiz") from exc
        if body.get("clear_key"):
            item.api_key = ""
        errors = validate(item, items)
        if errors:
            raise ValueError("; ".join(errors))
        if old and (old.endpoint, old.chat_model) != (item.endpoint, item.chat_model):
            item.last_test = {}  # the old result no longer describes this connection
        if "activate" in body:  # the editor's checkbox; quick model picks leave it as it was
            item.enabled = bool(body["activate"])
        if item.enabled and not item.roles:
            item.enabled = False
        clash = conflicts(items, item) if item.enabled else []
        if clash and not body.get("replace"):
            return self._conflict(item, clash)
        for other in clash:
            other.enabled = False
        items = [item if i.id == item.id else i for i in items] if old else [*items, item]
        self._store(items)
        return {"ok": True, "id": item.id, "state": self.state()}

    def set_active(self, body: dict[str, Any]) -> dict[str, Any]:
        items = self.items()
        item = self._find(items, body.get("id"))
        on = bool(body.get("enabled"))
        if on and not item.roles:
            raise ValueError("Önce bu entegrasyon için bir sohbet modeli seçin")
        clash = conflicts(items, item) if on else []
        if clash and not body.get("replace"):
            return self._conflict(item, clash)
        for other in clash:
            other.enabled = False
        item.enabled = on
        self._store(items)
        return {"ok": True, "state": self.state()}

    def delete(self, body: dict[str, Any]) -> dict[str, Any]:
        items = self.items()
        item = self._find(items, body.get("id"))
        self._store([i for i in items if i.id != item.id])
        return {"ok": True, "state": self.state()}

    @staticmethod
    def _conflict(item: Integration, clash: list[Integration]) -> dict[str, Any]:
        """Not saved: activating ``item`` would take a role another active one holds."""
        return {
            "ok": False,
            "conflict": [
                {"id": c.id, "name": c.name,
                 "roles": [ROLE_LABEL[r] for r in c.roles if r in item.roles]}
                for c in clash
            ],  # fmt: skip
        }

    # ------------------------------------------------------------------ servers

    def _candidate(self, body: dict[str, Any]) -> Integration:
        """The integration a test / model list is about: the form's values (unsaved) over
        the stored one; the stored key is used when the form leaves it blank."""
        items = self.items()
        old = self._find(items, body["id"]) if body.get("id") else None
        base = old.to_dict() if old else {}
        for k in ("name", "endpoint", "chat_model", "reasoning_effort"):
            if k in body:
                base[k] = str(body[k] or "").strip()
        for k, cast in (("temperature", float), ("timeout", int), ("seed", int)):
            if k in body:
                base[k] = cast(body[k])
        if body.get("api_key"):
            base["api_key"] = str(body["api_key"])
        base.setdefault("id", "")
        base.setdefault("name", "")
        base["endpoint"] = normalize_endpoint(str(base.get("endpoint", "")))
        if not base["endpoint"]:
            raise ValueError("API adresi girilmedi")
        return Integration(**base)

    @staticmethod
    def _client(item: Integration, timeout: float = 30) -> OpenAICompatibleClient:
        return OpenAICompatibleClient(
            item.endpoint, item.chat_model,
            temperature=item.temperature, timeout=timeout, api_key=item.api_key,
            reasoning_effort=item.reasoning_effort, seed=item.seed,
        )  # fmt: skip

    def _rows(self, item: Integration, timeout: float) -> list[dict[str, Any]]:
        models = self._client(item).list_models(timeout)
        for m in models:
            m["in_use"] = [CHAT] if item.enabled and m["id"] == item.chat_model else []
        return models

    def models(self, body: dict[str, Any]) -> dict[str, Any]:
        item = self._candidate(body)
        t0 = time.perf_counter()
        try:
            rows = self._rows(item, 10)
        except LLMError as exc:
            return {"ok": False, "error": str(exc), "models": []}
        return {"ok": True, "models": rows, "ms": round((time.perf_counter() - t0) * 1000)}

    def inventory(self) -> dict[str, Any]:
        """Every integration's models side by side, servers asked in parallel."""
        items = self.items()

        def one(item: Integration) -> dict[str, Any]:
            head = {"id": item.id, "name": item.name, "enabled": item.enabled}
            try:
                return {**head, "ok": True, "models": self._rows(item, INVENTORY_TIMEOUT)}
            except LLMError as exc:
                return {**head, "ok": False, "error": str(exc), "models": []}

        with ThreadPoolExecutor(max(1, min(8, len(items)))) as pool:
            return {"servers": list(pool.map(one, items))}

    def test(self, body: dict[str, Any]) -> dict[str, Any]:
        """Server and chat model — each step timed. With ``record`` the result
        is kept on the stored integration (the card's "Test et")."""
        item = self._candidate(body)
        client = self._client(item, min(item.timeout, TEST_CHAT_TIMEOUT))
        steps: list[dict[str, Any]] = []
        offered: list[str] = []

        def step(name: str, fn: Callable[[], tuple[bool, str]]) -> None:
            t0 = time.perf_counter()
            try:
                ok, detail = fn()
            except LLMError as exc:
                ok, detail = False, str(exc)
            ms = round((time.perf_counter() - t0) * 1000)
            steps.append({"name": name, "ok": ok, "detail": detail, "ms": ms})

        def server() -> tuple[bool, str]:
            offered.extend(client.ping())
            return True, f"Bağlantı kuruldu; sunucuda {len(offered)} model var"

        def missing(model: str) -> str:
            return "" if not offered or model in offered else " (model sunucunun listesinde yok)"

        def chat() -> tuple[bool, str]:
            reply = client.chat_json("Kısa ve doğru cevap ver. SADECE JSON döndür.",
                                     TEST_QUESTION, TEST_SCHEMA, max_tokens=60)  # fmt: skip
            if reply is None:
                why = client.last_error or "geçerli JSON dönmedi (düşünme modu açık olabilir)"
                return False, why[:300] + missing(item.chat_model)
            answer = str(reply.get("cevap", ""))[:40]
            return True, f"Cevap verdi: “{answer}”"

        step("Sunucu", server)
        if steps[0]["ok"] and item.chat_model:
            step(ROLE_LABEL[CHAT], chat)
        ok = all(s["ok"] for s in steps)
        if body.get("record") and item.id:
            items = self.items()
            stored = self._find(items, item.id)
            stored.last_test = {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "ok": ok,
                "summary": "; ".join(f"{s['name']}: {'✓' if s['ok'] else '✗'}" for s in steps),
            }
            write_integrations(self.path, items)  # a test changes no connection: no reload
        return {"ok": ok, "steps": steps}
