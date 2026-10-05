"""OpenAI-compatible client for a local model server (HANDOVER §10.3, ADR-008).

Works with LM Studio, vLLM, llama.cpp server and Ollama — anything serving
``/v1/chat/completions`` and ``/v1/embeddings``. Standard library only (closed network:
no extra wheels). ``NullClient`` keeps the app working when no model is configured, and
any LLM failure degrades to rule-based results instead of stopping a search.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import logging
import re
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from vsa import cancel, trace

log = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
# Qwen emits <think>, Gemma via Google AI Studio <thought> — often with a draft JSON inside.
_THINK = re.compile(r"<(think|thought)>.*?</\1>", re.DOTALL)


RETRY_CODES = (429, 500, 502, 503, 504)
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+)')
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


class LLMError(RuntimeError):
    pass


# ----------------------------------------------------------------- stoppable connections

CONNECT_TIMEOUT = 10.0  # seconds to open a connection; reading the answer has llm.timeout
HEALTH_TTL = 30.0  # a server check is reused this long
HEALTH_TIMEOUT = 5.0
# Server checks by address, shared by every client: the engine is rebuilt on each settings
# change, and a down server must not cost every admin action another wait.
_HEALTH: dict[str, tuple[float, str]] = {}


def _abort(conn: http.client.HTTPConnection) -> None:
    """Cut a connection from another thread: a blocked read returns at once, and the
    model server sees the client leave (LM Studio / vLLM stop generating)."""
    sock = conn.sock
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)
    conn.close()


def _stoppable(cls: type[http.client.HTTPConnection]) -> Callable[..., Any]:
    """Connection factory: connecting gives up after ``CONNECT_TIMEOUT`` (an unreachable
    server must not hold a question for the whole answer timeout), and the connection is
    cut when the analysis is stopped."""

    def make(host: str, **kwargs: Any) -> http.client.HTTPConnection:
        conn = cls(host, **kwargs)
        token = cancel.current()
        if token is not None:
            token.on_cancel(lambda: _abort(conn))
        connect = conn.connect

        def guarded_connect() -> None:
            full = conn.timeout
            if isinstance(full, int | float) and full > CONNECT_TIMEOUT:
                conn.timeout = CONNECT_TIMEOUT
            try:
                connect()
            finally:
                conn.timeout = full
            if conn.sock is not None and isinstance(full, int | float):
                conn.sock.settimeout(full)  # reading the answer may take its full time
            if token is not None and token.cancelled:  # a stop that came while connecting
                _abort(conn)
                raise OSError("analiz durduruldu")

        setattr(conn, "connect", guarded_connect)  # noqa: B010 - mypy: method assign
        return conn

    return make


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(_stoppable(http.client.HTTPConnection), req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        args: dict[str, Any] = {"context": getattr(self, "_context", None)}
        if hasattr(self, "_check_hostname"):  # Python 3.11
            args["check_hostname"] = self._check_hostname
        return self.do_open(_stoppable(http.client.HTTPSConnection), req, **args)


# Same as urlopen (proxies from the environment included), with stoppable connections.
_OPENER = urllib.request.build_opener(_HTTPHandler, _HTTPSHandler)


def retry_delay(header: str | None, body: str, attempt: int) -> float:
    """Seconds before retrying a rate-limited call: Retry-After, a ``retryDelay`` in the body,
    else exponential backoff; capped at 90 s."""
    for raw in (header, *_RETRY_DELAY.findall(body)[:1]):
        if raw and str(raw).strip().isdigit():
            return min(90.0, float(raw) + 1)
    return float(min(90, 5 * 2**attempt))


def _error_text(text: str) -> str:
    """The message of a JSON error body (OpenAI / Google style), else the text itself."""
    m = re.search(r'"(?:message|detail)"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    return (m.group(1) if m else text)[:300]


def fold_error(text: str) -> str:
    """Lower-cased ASCII of an API error message, for keyword checks."""
    return text.encode("ascii", "ignore").decode().translate(_ASCII_LOWER)


def _why(exc: BaseException) -> str:
    """A connection failure in words the settings screen can show."""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ConnectionRefusedError):
        return "bağlantı reddedildi — adres/port yanlış ya da sunucu kapalı"
    if isinstance(reason, TimeoutError | socket.timeout) or "timed out" in str(reason):
        return "sunucu zamanında yanıt vermedi — adres erişilemez olabilir"
    if isinstance(reason, socket.gaierror):
        return "sunucu adı çözülemedi — adresi kontrol edin"
    if isinstance(exc, json.JSONDecodeError):
        return "yanıt JSON değil — adres OpenAI uyumlu API'nin /v1 adresi mi?"
    return str(reason)


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

    def health(self) -> str:
        """"" when the chat model's server answers, else why not (Turkish, for people)."""
        ...


NO_MODEL = "Sohbet modeli bağlı değil"


class NullClient:
    """No model configured: every LLM step is skipped (ADR-008)."""

    available = False
    model = ""

    def health(self) -> str:
        return NO_MODEL

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
    (the analyst); with ``embeddings`` the server still serves the dense
    index even when chat is off. Nothing configured -> NullClient.

    ``llm.embedding_endpoint`` puts embeddings on a server of their own (vLLM serves one
    model per server); empty = the chat endpoint serves both, as LM Studio and Ollama do."""
    enabled = bool(getattr(llm, "enabled", False))
    endpoint = str(getattr(llm, "endpoint", ""))
    embed_endpoint = str(getattr(llm, "embedding_endpoint", "")) or endpoint
    want_embed = embeddings and bool(getattr(llm, "embedding_model", "")) and bool(embed_endpoint)
    want_chat = enabled and bool(endpoint)
    if not (want_chat or want_embed):
        return NullClient()
    if embed_endpoint == endpoint:
        return OpenAICompatibleClient(
            endpoint=endpoint,
            model=llm.model if want_chat else "",
            embedding_model=llm.embedding_model if want_embed else "",
            temperature=llm.temperature,
            timeout=llm.timeout,
            api_key=llm.api_key,
            reasoning_effort=llm.reasoning_effort,
            seed=getattr(llm, "seed", -1),
        )
    chat: LLMClient = NullClient()
    if want_chat:
        chat = OpenAICompatibleClient(
            endpoint=endpoint, model=llm.model, temperature=llm.temperature,
            timeout=llm.timeout, api_key=llm.api_key, reasoning_effort=llm.reasoning_effort,
            seed=getattr(llm, "seed", -1),
        )  # fmt: skip
    embedder: LLMClient = NullClient()
    if want_embed:
        embedder = OpenAICompatibleClient(
            endpoint=embed_endpoint, model="", embedding_model=llm.embedding_model,
            timeout=llm.timeout, api_key=getattr(llm, "embedding_api_key", "") or llm.api_key,
        )  # fmt: skip
    return SplitClient(chat, embedder)


def embedding_client(llm: Any, timeout: float = 600.0) -> OpenAICompatibleClient:
    """Client for building the dense index: the embedding server and model of ``llm``
    (``LLMSettings``). Raises ``LLMError`` when no embedding model is configured."""
    endpoint = str(getattr(llm, "embedding_endpoint", "")) or str(getattr(llm, "endpoint", ""))
    model = str(getattr(llm, "embedding_model", ""))
    if not (endpoint and model):
        raise LLMError("Embedding modeli bağlı değil (Yapay zekâ → embedding rolü)")
    key = str(getattr(llm, "embedding_api_key", "")) or str(getattr(llm, "api_key", ""))
    return OpenAICompatibleClient(endpoint, "", model, timeout=timeout, api_key=key)


class SplitClient:
    """Chat from one server, embeddings from another (``llm.embedding_endpoint``)."""

    def __init__(self, chat: LLMClient, embedder: LLMClient) -> None:
        self.chat = chat
        self.embedder = embedder

    @property
    def available(self) -> bool:
        return self.chat.available

    @property
    def model(self) -> str:
        return self.chat.model

    @property
    def last_error(self) -> str:
        return str(getattr(self.chat, "last_error", ""))

    def health(self) -> str:
        return self.chat.health()

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        *,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        return self.chat.chat_json(system, user, schema, max_tokens=max_tokens)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embedder.embed(texts)


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
        seed: int | None = None,
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
        self.seed = seed if seed is not None and seed >= 0 else None
        self.system_role = True
        self.structured = True
        self.calls = 0
        self.failures = 0
        self.seconds = 0.0
        self.prompt_tokens = 0  # as reported by the server ("usage"), for hosted quotas
        self.completion_tokens = 0
        self.last_error = ""  # why the last chat call failed, for the user (ADR-029 fallback)

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
            cancel.check()
            try:
                with _OPENER.open(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                cancel.check()
                detail = exc.read().decode("utf-8", "replace")[:600]
                if exc.code in RETRY_CODES and attempt < self.retries:
                    wait = retry_delay(exc.headers.get("Retry-After"), detail, attempt)
                    log.warning("HTTP %s, %.0f sn sonra yeniden denenecek", exc.code, wait)
                    with trace.span(f"HTTP {exc.code} — bekleme", _error_text(detail),
                                    trace.EVENT) as s:  # fmt: skip
                        if s is not None:
                            s.status = "warn"
                        cancel.sleep(wait)
                    continue
                raise LLMError(f"{path}: HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError,
                    http.client.HTTPException) as exc:  # fmt: skip
                cancel.check()  # a cut connection is the stop, not a model failure
                raise LLMError(f"{path}: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError(f"{path}: beklenmeyen yanıt")
        return data

    def _get(self, url: str, timeout: float) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            with _OPENER.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            hint = " (API anahtarı eksik veya geçersiz)" if exc.code in (401, 403) else ""
            raise LLMError(f"Sunucu HTTP {exc.code} döndürdü{hint}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError,
                http.client.HTTPException) as exc:  # fmt: skip
            raise LLMError(f"Model sunucusuna ulaşılamadı ({self.endpoint}): {_why(exc)}") from exc
        if not isinstance(data, dict):
            raise LLMError("Sunucu beklenmeyen bir yanıt döndürdü")
        return data

    def ping(self) -> list[str]:
        """Model ids the server offers (raises LLMError when unreachable)."""
        return [str(m.get("id")) for m in self._get(f"{self.endpoint}/models", 10).get("data", [])]

    def health(self) -> str:
        """Is the chat model's server there? A quick ``/models`` call, reused for
        ``HEALTH_TTL`` seconds, so a question does not wait on a dead server."""
        if not self.available:
            return NO_MODEL
        now = time.monotonic()
        seen = _HEALTH.get(self.endpoint)
        if seen is not None and now - seen[0] < HEALTH_TTL:
            return seen[1]
        try:  # reachability only: some servers (Ollama) accept names their list spells otherwise
            self._get(f"{self.endpoint}/models", HEALTH_TIMEOUT)
            reason = ""
        except LLMError as exc:
            reason = str(exc)
        _HEALTH[self.endpoint] = (now, reason)
        return reason

    def list_models(self, timeout: float = 10) -> list[dict[str, Any]]:
        """The server's model inventory: id plus whatever the server tells about each one —
        type and load state (LM Studio's REST API), context length (vLLM ``max_model_len``,
        LM Studio ``max_context_length``), owner. Raises LLMError when unreachable."""
        base = self.endpoint[: -len("/v1")] if self.endpoint.endswith("/v1") else ""
        rich: dict[str, dict[str, Any]] = {}
        if base:  # LM Studio only; other servers answer 404 and the plain list is enough
            with contextlib.suppress(LLMError):
                rich = {str(m.get("id")): m for m in
                        self._get(f"{base}/api/v0/models", 3).get("data", [])}  # fmt: skip
        out = []
        for m in self._get(f"{self.endpoint}/models", timeout).get("data", []):
            mid = str(m.get("id", ""))
            extra = rich.get(mid, {})
            ctx = extra.get("max_context_length") or m.get("max_model_len") or m.get(
                "context_length") or m.get("context_window")  # fmt: skip
            out.append({
                "id": mid,
                "type": str(extra.get("type", "")),
                "loaded": (extra.get("state") == "loaded") if extra else None,
                "context": int(ctx) if isinstance(ctx, int | float) else None,
                "owner": str(m.get("owned_by", "") or extra.get("publisher", "")),
                "quant": str(extra.get("quantization", "")),
            })  # fmt: skip
        return out

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
        with trace.span("LLM çağrısı", self._model, trace.LLM) as s:
            reply = self._chat_json(system, user, schema, max_tokens)
            if s is not None and reply is None:
                s.status, s.detail = "error", f"{self._model} — {self.last_error[:300]}"
            return reply

    def _chat_json(
        self, system: str, user: str, schema: Mapping[str, Any], max_tokens: int
    ) -> dict[str, Any] | None:
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
            if self.seed is not None:
                body["seed"] = self.seed
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
                trace.count(requests=1, prompt_tokens=int(usage.get("prompt_tokens") or 0),
                            completion_tokens=int(usage.get("completion_tokens") or 0))  # fmt: skip
                content = str(data["choices"][0]["message"].get("content") or "")
            except LLMError as exc:
                if adaptations < 3 and self._adapt(str(exc)):
                    adaptations += 1
                    continue  # same attempt, without the feature the model refused
                self.failures += 1
                self.last_error = str(exc)
                log.warning("LLM çağrısı başarısız: %s", exc)
                return None
            except (KeyError, IndexError) as exc:
                self.failures += 1
                self.last_error = f"beklenmeyen yanıt ({exc})"
                log.warning("LLM çağrısı başarısız: %s", exc)
                return None
            finally:
                self.seconds += time.perf_counter() - started
            attempt += 1
            parsed = parse_json_reply(content)
            if parsed is not None:
                return parsed
            log.warning("LLM yanıtı JSON değil (deneme %d)", attempt)
            trace.event("Yanıt JSON değil — onarım isteniyor", content[:200])
            messages = [
                *messages,
                {"role": "assistant", "content": content[:2000]},
                {
                    "role": "user",
                    "content": "Yanıtın geçerli JSON değil. SADECE şemaya uyan JSON döndür.",
                },
            ]
        self.failures += 1
        self.last_error = "model geçerli JSON üretmedi"
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
        elif self.seed is not None and "seed" in text:
            self.seed = None
        else:
            return False
        log.info("Model bir özelliği desteklemiyor, onsuz yeniden deneniyor: %s", error[:160])
        trace.event("Model bir özelliği reddetti — onsuz yeniden", _error_text(error))
        return True

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.embedding_model:
            raise LLMError("Embedding modeli yapılandırılmadı")
        with trace.span("Embedding", f"{self.embedding_model} · {len(texts)} metin", trace.EMBED):
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
