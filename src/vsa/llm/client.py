"""OpenAI-compatible client for a local model server (HANDOVER §10.3, ADR-008).

Works with LM Studio, vLLM, llama.cpp server and Ollama — anything serving
``/v1/chat/completions`` and ``/v1/embeddings``. Standard library only (closed network:
no extra wheels). ``NullClient`` keeps the app working when no model is configured, and
any LLM failure degrades to rule-based results instead of stopping a search.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

log = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def model(self) -> str: ...

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class NullClient:
    """No model configured: every LLM step is skipped (ADR-008)."""

    available = False
    model = ""

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        return None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise LLMError("Embedding modeli yapılandırılmadı")


def parse_json_reply(text: str) -> dict[str, Any] | None:
    """Tolerant JSON extraction: strips <think> blocks and markdown fences."""
    text = _THINK.sub("", text).strip()
    text = _FENCE.sub("", text).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def client_from_settings(llm: Any, embeddings: bool = False) -> LLMClient:
    """``LLMSettings`` -> client (ADR-008). ``llm.enabled`` governs the chat features
    (judge, query expansion); with ``embeddings`` the endpoint still serves the dense
    index even when chat is off. Nothing configured -> NullClient."""
    enabled = bool(getattr(llm, "enabled", False))
    want_embed = embeddings and bool(getattr(llm, "embedding_model", ""))
    if not getattr(llm, "endpoint", "") or not (enabled or want_embed):
        return NullClient()
    return OpenAICompatibleClient(
        endpoint=llm.endpoint,
        model=llm.model if enabled else "",
        embedding_model=llm.embedding_model,
        temperature=llm.temperature,
        timeout=llm.timeout,
        api_key=llm.api_key,
        reasoning_effort=llm.reasoning_effort,
    )


class OpenAICompatibleClient:
    def __init__(
        self,
        endpoint: str,
        model: str,
        embedding_model: str = "",
        temperature: float = 0.1,
        timeout: float = 120.0,
        api_key: str = "",
        reasoning_effort: str = "none",
    ) -> None:
        # "localhost" resolves to ::1 first on Windows; servers listening on IPv4 only
        # (LM Studio) then cost ~2 s per request before the fallback. Use IPv4 directly.
        self.endpoint = endpoint.rstrip("/").replace("://localhost", "://127.0.0.1")
        self._model = model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.timeout = timeout
        self.api_key = api_key
        # Reasoning models (Qwen3.x) otherwise spend the whole budget "thinking" and return
        # empty content; "none" makes them answer directly. Ignored by other models.
        self.reasoning_effort = reasoning_effort
        self.calls = 0
        self.failures = 0
        self.seconds = 0.0

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self._model)

    @property
    def model(self) -> str:
        return self._model

    def _post(self, path: str, body: Mapping[str, Any], timeout: float) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.endpoint}{path}", data=json.dumps(body).encode("utf-8"), headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise LLMError(f"{path}: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError(f"{path}: beklenmeyen yanıt")
        return data

    def ping(self) -> list[str]:
        """Model ids the server offers (raises LLMError when unreachable)."""
        req = urllib.request.Request(f"{self.endpoint}/models")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise LLMError(f"Model sunucusuna ulaşılamadı ({self.endpoint}): {exc}") from exc
        return [str(m.get("id")) for m in data.get("data", [])]

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        """Schema-constrained JSON (HANDOVER §10.4); one repair attempt, then None (§10.6)."""
        if not self.available:
            return None
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            **({"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}),
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": dict(schema)},
            },
        }
        for attempt in range(2):
            started = time.perf_counter()
            self.calls += 1
            try:
                data = self._post("/chat/completions", body, self.timeout)
                content = str(data["choices"][0]["message"].get("content") or "")
            except (LLMError, KeyError, IndexError) as exc:
                self.failures += 1
                log.warning("LLM çağrısı başarısız: %s", exc)
                return None
            finally:
                self.seconds += time.perf_counter() - started
            parsed = parse_json_reply(content)
            if parsed is not None:
                return parsed
            log.warning("LLM yanıtı JSON değil (deneme %d)", attempt + 1)
            messages = [
                *messages,
                {"role": "assistant", "content": content[:2000]},
                {
                    "role": "user",
                    "content": "Yanıtın geçerli JSON değil. SADECE şemaya uyan JSON döndür.",
                },
            ]
            body["messages"] = messages
        self.failures += 1
        return None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.embedding_model:
            raise LLMError("Embedding modeli yapılandırılmadı")
        data = self._post(
            "/embeddings",
            {"model": self.embedding_model, "input": list(texts)},
            max(self.timeout, 600.0),
        )
        rows = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
        vectors = [[float(x) for x in r["embedding"]] for r in rows]
        if len(vectors) != len(texts):
            raise LLMError("Embedding yanıtında eksik vektör")
        return vectors
