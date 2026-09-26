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


RETRY_CODES = (429, 500, 502, 503, 504)
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+)')
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


class LLMError(RuntimeError):
    pass


def retry_delay(header: str | None, body: str, attempt: int) -> float:
    """Seconds before retrying a rate-limited call: Retry-After, a ``retryDelay`` in the body,
    else exponential backoff; capped at 90 s."""
    for raw in (header, *_RETRY_DELAY.findall(body)[:1]):
        if raw and str(raw).strip().isdigit():
            return min(90.0, float(raw) + 1)
    return float(min(90, 5 * 2**attempt))


def fold_error(text: str) -> str:
    """Lower-cased ASCII of an API error message, for keyword checks."""
    return text.encode("ascii", "ignore").decode().translate(_ASCII_LOWER)


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
        retries: int = 0,
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
        # Hosted APIs (ADR-026): retry rate limits; some models (Gemma on Google AI Studio)
        # take neither a system message nor a JSON schema — learned from the first 400.
        self.retries = retries
        self.system_role = True
        self.structured = True
        self.calls = 0
        self.failures = 0
        self.seconds = 0.0
        self.prompt_tokens = 0  # as reported by the server ("usage"), for hosted quotas
        self.completion_tokens = 0

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
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:600]
                if exc.code in RETRY_CODES and attempt < self.retries:
                    wait = retry_delay(exc.headers.get("Retry-After"), detail, attempt)
                    log.warning("HTTP %s, %.0f sn sonra yeniden denenecek", exc.code, wait)
                    time.sleep(wait)
                    continue
                raise LLMError(f"{path}: HTTP {exc.code}: {detail}") from exc
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

        def build(messages: list[dict[str, str]]) -> dict[str, Any]:
            if not self.system_role:  # fold the instructions into the first user turn
                first = {"role": "user", "content": f"{system}\n\n{messages[1]['content']}"}
                messages = [first, *messages[2:]]
            body: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": max_tokens,
            }
            if self.reasoning_effort:
                body["reasoning_effort"] = self.reasoning_effort
            if self.structured:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "result", "strict": True, "schema": dict(schema)},
                }
            return body

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        attempt = adaptations = 0
        while attempt < 2:
            started = time.perf_counter()
            self.calls += 1
            try:
                data = self._post("/chat/completions", build(messages), self.timeout)
                usage = data.get("usage") or {}
                self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
                self.completion_tokens += int(usage.get("completion_tokens") or 0)
                content = str(data["choices"][0]["message"].get("content") or "")
            except LLMError as exc:
                if adaptations < 3 and self._adapt(str(exc)):
                    adaptations += 1
                    continue  # same attempt, without the feature the model refused
                self.failures += 1
                log.warning("LLM çağrısı başarısız: %s", exc)
                return None
            except (KeyError, IndexError) as exc:
                self.failures += 1
                log.warning("LLM çağrısı başarısız: %s", exc)
                return None
            finally:
                self.seconds += time.perf_counter() - started
            attempt += 1
            parsed = parse_json_reply(content)
            if parsed is not None:
                return parsed
            log.warning("LLM yanıtı JSON değil (deneme %d)", attempt)
            messages = [
                *messages,
                {"role": "assistant", "content": content[:2000]},
                {
                    "role": "user",
                    "content": "Yanıtın geçerli JSON değil. SADECE şemaya uyan JSON döndür.",
                },
            ]
        self.failures += 1
        return None

    def _adapt(self, error: str) -> bool:
        """Drop a request feature the model rejected with HTTP 400; True if a retry helps."""
        if "HTTP 400" not in error:
            return False
        text = fold_error(error)
        if self.system_role and ("developer instruction" in text or "system instruction" in text):
            self.system_role = False
        elif self.structured and any(
            k in text for k in ("json mode", "response_format", "response_mime_type", "schema")
        ):
            self.structured = False
        elif self.reasoning_effort and ("reasoning" in text or "thinking" in text):
            self.reasoning_effort = ""
        else:
            return False
        log.info("Model bir özelliği desteklemiyor, onsuz yeniden deneniyor: %s", error[:160])
        return True

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
