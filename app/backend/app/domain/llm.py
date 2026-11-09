"""Model connection rules, failure classes and the model port (data-dictionary 003-llm-connection).

The analyst, the connection test and the measurement script reach the in-house model server only
through ``LlmChatPort`` (Decision 1): a chat call, a health check and a model list over the
OpenAI-compatible API (Decision 2). A failure is one of the fixed classes of Requirement 13; its
short test and check texts come from the table here and never from the server, the address or an
exception. The reason an analysis shows is derived from the class by question-analysis
(its Requirement 5).
Prompts, schemas, model replies and the API key stay out of every ``repr``, log, signal and
summary.
"""

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit

# --- Fixed values (Requirement 1: constants, not settings) -------------------------------------

USER_AGENT = "DWHNavigator-Backend/1.0 (internal data dictionary; httpx)"
CONNECT_TIMEOUT_SECONDS = 10.0
HEALTH_TIMEOUT_SECONDS = 5.0
HEALTH_TTL_SECONDS = 30.0
MODEL_LIST_TIMEOUT_SECONDS = 10.0
LM_STUDIO_TIMEOUT_SECONDS = 3.0
INVENTORY_TIMEOUT_SECONDS = 6.0
INVENTORY_PARALLEL = 8
TEST_CHAT_TIMEOUT_SECONDS = 30.0
# Requirement 9: total ceilings of the administration calls that run inside one HTTP request.
MODEL_LIST_BUDGET_SECONDS = 10.0
TEST_SERVER_BUDGET_SECONDS = 10.0
TEST_CHAT_BUDGET_SECONDS = 30.0
INVENTORY_SERVER_BUDGET_SECONDS = 10.0
INVENTORY_BUDGET_SECONDS = 50.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

# Requirement 7 and 8: at most three dropped features and two model replies per chat call.
MAX_ADAPTATIONS = 3
MAX_REPLIES = 2
ERROR_TEXT_CHARS = 600
REPAIR_REPLY_CHARS = 2000
REPAIR_PROMPT = "Yanıtın geçerli JSON değil. SADECE şemaya uyan JSON döndür."
# Target only: when the admin sets thinking off (``reasoning_effort: "none"``), every request also
# asks the model's chat template to turn thinking off, from the first request on. Servers such as
# vLLM accept ``reasoning_effort`` silently for Qwen and keep thinking, which filled the reply
# budget. ``enable_thinking`` is the switch of the Qwen3, GLM and Hunyuan templates, ``thinking``
# that of the DeepSeek-V3.1 and Granite templates; a template ignores a name it does not use. A
# server that refuses the field gets the request again without it (Requirement 7).
THINKING_OFF_KWARGS: Mapping[str, Any] = {"enable_thinking": False, "thinking": False}

# Requirement 15: the connection test's chat step, as in the source.
SERVER_STEP = "Sunucu"
CHAT_STEP = "Sohbet modeli"
TEST_SYSTEM_PROMPT = "Kısa ve doğru cevap ver. SADECE JSON döndür."
TEST_QUESTION = "Türkiye'nin başkenti neresidir?"
TEST_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {"cevap": {"type": "string"}},
    "required": ["cevap"],
    "additionalProperties": False,
}
TEST_MAX_TOKENS = 60
TEST_ANSWER_CHARS = 40
MODEL_NOT_LISTED = " (model sunucunun listesinde yok)"

# Requirement 2 and Decision 17.
NAME_MAX_LENGTH = 100
ENDPOINT_MAX_LENGTH = 2048
CHAT_MODEL_MAX_LENGTH = 256
API_KEY_MAX_LENGTH = 4096
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0
DEFAULT_TEMPERATURE = 0.0
TIMEOUT_MIN_SECONDS = 5
TIMEOUT_MAX_SECONDS = 3600
DEFAULT_TIMEOUT_SECONDS = 900
REASONING_EFFORTS = ("none", "low", "medium", "high", "")
DEFAULT_REASONING_EFFORT = "none"
SEED_MIN = -1
SEED_MAX = 2147483647
DEFAULT_SEED = 42
MAX_INTEGRATIONS = 50

RuntimeEnvironment = Literal["local", "nonprod"]


class LlmOutcome(StrEnum):
    """``ok`` or the fixed failure class of a call or a check (Requirement 13)."""

    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    KEY_UNREADABLE = "key_unreadable"
    NETWORK_POLICY_DENIED = "network_policy_denied"
    NAME_UNRESOLVED = "name_unresolved"
    CONNECT_REFUSED = "connect_refused"
    CONNECT_ERROR = "connect_error"
    TLS_ERROR = "tls_error"
    TIMEOUT = "timeout"
    UNAUTHORIZED = "unauthorized"
    CONTEXT_EXCEEDED = "context_exceeded"
    UPSTREAM_STATUS = "upstream_status"
    INVALID_RESPONSE = "invalid_response"
    OUTPUT_TRUNCATED = "output_truncated"
    INVALID_JSON = "invalid_json"
    RESPONSE_TOO_LARGE = "response_too_large"
    CANCELLED = "cancelled"


class LlmPurpose(StrEnum):
    """Who made a chat call (Requirement 18)."""

    ANALYSIS = "analysis"
    CONNECTION_TEST = "connection_test"
    EVALUATION = "evaluation"
    DICTIONARY_SYNC = "dictionary_sync"


class ProbeOperation(StrEnum):
    """The ``/models`` reads (Requirement 12 and 14)."""

    HEALTH = "health"
    MODELS = "models"
    INVENTORY = "inventory"


class AdaptedFeature(StrEnum):
    """A request feature the server refused with HTTP 400, in rule order (Requirement 7)."""

    SYSTEM_ROLE = "system_role"
    RESPONSE_FORMAT = "response_format"
    REASONING_EFFORT = "reasoning_effort"
    SEED = "seed"
    CHAT_TEMPLATE_KWARGS = "chat_template_kwargs"


# --- Requirement 13: fixed Turkish texts --------------------------------------------------------

_UNREACHABLE = "Model sunucusuna ulaşılamadı"
_KEY_HINT = " (API anahtarı eksik veya geçersiz)"
_SHORT_REASONS: dict[LlmOutcome, str] = {
    LlmOutcome.NOT_CONFIGURED: "Sohbet modeli bağlı değil",
    LlmOutcome.KEY_UNREADABLE: "Kayıtlı API anahtarı okunamadı; anahtarı yeniden girin",
    LlmOutcome.NETWORK_POLICY_DENIED: "adres kurum ağı dışında; istek gönderilmedi",
    LlmOutcome.NAME_UNRESOLVED: "sunucu adı çözülemedi — adresi kontrol edin",
    LlmOutcome.CONNECT_REFUSED: "bağlantı reddedildi — adres/port yanlış ya da sunucu kapalı",
    LlmOutcome.CONNECT_ERROR: "bağlantı kurulamadı",
    LlmOutcome.TLS_ERROR: "güvenli bağlantı kurulamadı — sunucu sertifikası doğrulanamadı",
    LlmOutcome.TIMEOUT: "sunucu zamanında yanıt vermedi — adres erişilemez olabilir",
    LlmOutcome.CONTEXT_EXCEEDED: "modelin bağlam penceresi yetmedi",
    LlmOutcome.OUTPUT_TRUNCATED: "model cevabı uzunluk sınırında kesildi",
    LlmOutcome.INVALID_JSON: "model geçerli JSON üretmedi",
    LlmOutcome.RESPONSE_TOO_LARGE: "yanıt izin verilen boyutu aştı",
    LlmOutcome.CANCELLED: "durduruldu",
}
_PROBE_INVALID_RESPONSE = "yanıt JSON değil — adres OpenAI uyumlu API'nin /v1 adresi mi?"
_CHAT_INVALID_RESPONSE = "beklenmeyen yanıt"
# A check that fails with one of these classes did not reach a working API at the address.
_UNREACHABLE_CLASSES = frozenset(
    {
        LlmOutcome.NETWORK_POLICY_DENIED,
        LlmOutcome.NAME_UNRESOLVED,
        LlmOutcome.CONNECT_REFUSED,
        LlmOutcome.CONNECT_ERROR,
        LlmOutcome.TLS_ERROR,
        LlmOutcome.TIMEOUT,
        LlmOutcome.INVALID_RESPONSE,
    }
)


def _status_text(http_status: int | None) -> str:
    return f"Sunucu HTTP {http_status if http_status is not None else '?'} döndürdü"


def short_reason(outcome: LlmOutcome, http_status: int | None = None, *, probe: bool) -> str:
    """The short reason of a test step or a check; ``probe`` for a ``/models`` read."""

    if outcome is LlmOutcome.OK:
        return ""
    if outcome is LlmOutcome.UNAUTHORIZED:
        return _status_text(http_status) + _KEY_HINT
    if outcome is LlmOutcome.UPSTREAM_STATUS:
        return _status_text(http_status)
    if outcome is LlmOutcome.INVALID_RESPONSE:
        return _PROBE_INVALID_RESPONSE if probe else _CHAT_INVALID_RESPONSE
    return _SHORT_REASONS[outcome]


def probe_message(outcome: LlmOutcome, http_status: int | None = None) -> str:
    """The message of a failed health check, model list or inventory server (Requirement 13)."""

    reason = short_reason(outcome, http_status, probe=True)
    if outcome in _UNREACHABLE_CLASSES:
        return f"{_UNREACHABLE}: {reason}"
    return reason


# --- Requirement 7 and 8: reading the server ----------------------------------------------------

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
# Qwen writes <think>, Gemma through some servers <thought>, often with a draft JSON inside.
_THINK = re.compile(r"<(think|thought)>.*?</\1>", re.DOTALL)


def parse_json_reply(text: str) -> dict[str, Any] | None:
    """The JSON object of a model reply, as the source's ``parse_json_reply``; None otherwise."""

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


def refused_feature(
    folded_error: str,
    *,
    system_role: bool,
    structured: bool,
    reasoning_effort: str,
    seed: int | None,
    thinking_off: bool = False,
) -> AdaptedFeature | None:
    """The first Requirement 7 rule a 400 body matches among the features still sent.

    ``thinking_off`` is the target-only ``chat_template_kwargs`` field. An error that names the
    field itself drops it before the effort rule (whose word "thinking" would match it too);
    otherwise its rule comes last, so the four source rules keep their order and precedence.
    """

    text = folded_error
    if system_role and ("developer instruction" in text or "system instruction" in text):
        return AdaptedFeature.SYSTEM_ROLE
    if structured and any(
        word in text for word in ("json mode", "response_format", "response_mime_type", "schema")
    ):
        return AdaptedFeature.RESPONSE_FORMAT
    if thinking_off and ("chat_template_kwargs" in text or "enable_thinking" in text):
        return AdaptedFeature.CHAT_TEMPLATE_KWARGS
    if reasoning_effort and ("reasoning" in text or "thinking" in text):
        return AdaptedFeature.REASONING_EFFORT
    if seed is not None and "seed" in text:
        return AdaptedFeature.SEED
    if thinking_off and any(
        word in text for word in ("chat_template_kwargs", "enable_thinking", "template")
    ):
        return AdaptedFeature.CHAT_TEMPLATE_KWARGS
    return None


def context_exceeded(folded_error: str) -> bool:
    """Requirement 13: the server says the request did not fit the model's context window."""

    return "context" in folded_error and any(
        word in folded_error for word in ("exceed", "size", "length")
    )


# --- Requirement 2: integration fields ----------------------------------------------------------

_ENDPOINT_FORMAT = "API adresi http:// veya https:// ile başlayan tam bir adres olmalı (ör. http://10.0.0.5:8000/v1)"
_ENDPOINT_PARTS = "API adresi kullanıcı adı, parola, sorgu veya # parçası içeremez"
_ENDPOINT_HTTPS_ONLY = "Bu ortamda API adresi https:// ile başlamalı"
_NUMBER_INVALID = "Sayısal alanlardan biri geçersiz"
ENDPOINT_MISSING = "API adresi girilmedi"


class LlmIntegrationInvalid(ValueError):
    """Requirement 2 format errors; ``message`` joins them with ``"; "`` as the source does."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("integration fields are invalid")
        self.problems = tuple(problems)

    @property
    def message(self) -> str:
        return "; ".join(self.problems)


def _too_long(label: str, limit: int) -> str:
    return f"{label} en çok {limit} karakter olabilir"


def _has_control(text: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in text)


def normalize_endpoint(raw: str) -> str:
    """Trim, drop a trailing ``/`` and a pasted ``/chat/completions`` or ``/models``."""

    url = raw.strip().rstrip("/")
    for tail in ("/chat/completions", "/models"):
        url = url.removesuffix(tail)
    return url


def _split(endpoint: str) -> tuple[SplitResult, int] | None:
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if port is None:
        port = 443 if parts.scheme == "https" else 80
    if not 1 <= port <= 65535:
        return None
    return parts, port


def endpoint_problem(endpoint: str, environment: RuntimeEnvironment) -> str | None:
    """The one Requirement 2 message an already normalized address earns, or None."""

    if len(endpoint) > ENDPOINT_MAX_LENGTH:
        return _too_long("API adresi", ENDPOINT_MAX_LENGTH)
    if any(character.isspace() for character in endpoint) or _has_control(endpoint):
        return _ENDPOINT_FORMAT
    split = _split(endpoint)
    if split is None:
        return _ENDPOINT_FORMAT
    parts, _port = split
    if (
        parts.username is not None
        or parts.password is not None
        or "@" in parts.netloc
        or "?" in endpoint
        or "#" in endpoint
    ):
        return _ENDPOINT_PARTS
    if environment == "nonprod" and parts.scheme != "https":
        return _ENDPOINT_HTTPS_ONLY
    return None


def endpoint_origin(endpoint: str) -> str:
    """Scheme, host and port of a valid address: the boundary of a saved API key (Decision 9)."""

    split = _split(endpoint)
    if split is None:
        raise ValueError("not a valid endpoint")
    parts, port = split
    host = (parts.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    return f"{parts.scheme}://{host}:{port}"


def endpoint_url(endpoint: str, path: str) -> str:
    """``path`` appended to the address's path; the address carries no query or fragment."""

    parts = urlsplit(endpoint)
    return urlunsplit((parts.scheme, parts.netloc, parts.path + path, "", ""))


def lm_studio_models_url(endpoint: str) -> str | None:
    """LM Studio's detail list ``<root>/api/v0/models`` when the address ends with ``/v1``."""

    parts = urlsplit(endpoint)
    if not parts.path.endswith("/v1"):
        return None
    root = parts.path[: -len("/v1")]
    return urlunsplit((parts.scheme, parts.netloc, root + "/api/v0/models", "", ""))


def _number(value: object, kind: Literal["float", "int"]) -> float | int:
    """The source's ``float()``/``int()`` reading; a non-integral or bool value is refused."""

    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError("not a number")
    if kind == "float":
        return float(value)
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("not integral")
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    return value


@dataclass(frozen=True, slots=True)
class IntegrationFields:
    """Validated values of one integration; the API key is checked but kept elsewhere."""

    name: str
    endpoint: str
    chat_model: str
    temperature: float
    timeout_seconds: int
    reasoning_effort: str
    seed: int


def check_integration_fields(
    *,
    name: str,
    endpoint: str,
    chat_model: str,
    temperature: object,
    timeout_seconds: object,
    reasoning_effort: str,
    seed: object,
    api_key: str | None,
    environment: RuntimeEnvironment,
    check_name: bool = True,
) -> IntegrationFields:
    """Requirement 2: trimmed and normalized values, or every format problem at once."""

    try:
        temperature_value = float(_number(temperature, "float"))
        timeout_value = int(_number(timeout_seconds, "int"))
        seed_value = int(_number(seed, "int"))
    except (TypeError, ValueError, OverflowError):
        # As in the source: a value that is not a number answers with this message alone.
        raise LlmIntegrationInvalid([_NUMBER_INVALID]) from None
    problems: list[str] = []
    name = name.strip()
    if check_name:
        if not name:
            problems.append("Ad boş olamaz")
        elif len(name) > NAME_MAX_LENGTH:
            problems.append(_too_long("Ad", NAME_MAX_LENGTH))
        elif _has_control(name):
            problems.append("Ad geçersiz karakter içeriyor")
    endpoint = normalize_endpoint(endpoint)
    endpoint_message = endpoint_problem(endpoint, environment)
    if endpoint_message is not None:
        problems.append(endpoint_message)
    chat_model = chat_model.strip()
    if len(chat_model) > CHAT_MODEL_MAX_LENGTH:
        problems.append(_too_long("Sohbet modeli", CHAT_MODEL_MAX_LENGTH))
    elif _has_control(chat_model):
        problems.append("Sohbet modeli geçersiz karakter içeriyor")
    if not TEMPERATURE_MIN <= temperature_value <= TEMPERATURE_MAX:
        problems.append("Sıcaklık 0 ile 2 arasında olmalı")
    if not TIMEOUT_MIN_SECONDS <= timeout_value <= TIMEOUT_MAX_SECONDS:
        problems.append("Zaman aşımı 5 ile 3600 saniye arasında olmalı")
    if reasoning_effort not in REASONING_EFFORTS:
        problems.append("Düşünme modu geçersiz")
    if not SEED_MIN <= seed_value <= SEED_MAX:
        problems.append("Seed -1 ile 2147483647 arasında olmalı")
    if api_key:
        if len(api_key) > API_KEY_MAX_LENGTH:
            problems.append(_too_long("API anahtarı", API_KEY_MAX_LENGTH))
        elif any(character.isspace() for character in api_key) or _has_control(api_key):
            problems.append("API anahtarı geçersiz karakter içeriyor")
    if problems:
        raise LlmIntegrationInvalid(problems)
    return IntegrationFields(
        name=name,
        endpoint=endpoint,
        chat_model=chat_model,
        temperature=temperature_value,
        timeout_seconds=timeout_value,
        reasoning_effort=reasoning_effort,
        seed=seed_value,
    )


# --- Requirement 5: the connection snapshot -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class LlmConnection:
    """One connection as an analysis, a test or a model list uses it; the key stays out of repr.

    ``public_id`` is empty for a test of unsaved form values.
    """

    endpoint: str
    chat_model: str = ""
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    seed: int = DEFAULT_SEED
    api_key: str | None = field(default=None, repr=False)
    public_id: str | None = None
    # Whose call this is, for the LLM call log; a connection without it is not logged.
    tenant_id: int | None = None
    # The generation role of the same server (dictionary updates): empty / 'inherit' use the
    # chat model's own model and reasoning.
    generation_model: str = ""
    generation_reasoning_effort: str = "inherit"
    judge_reasoning_effort: str = "inherit"

    @property
    def fingerprint(self) -> str:
        """Changes when any connection field changes; keys the learned features and health."""

        fields = [
            self.endpoint,
            self.api_key or "",
            self.chat_model,
            repr(self.temperature),
            self.timeout_seconds,
            self.reasoning_effort,
            self.seed,
        ]
        encoded = json.dumps(fields, ensure_ascii=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def sampling(self) -> tuple[str, float, str, int]:
        """Model, temperature, reasoning effort and seed: the saved-answer fingerprint fields."""

        return (self.chat_model, self.temperature, self.reasoning_effort, self.seed)


# --- Requirement 18: results and the content-free call summary ---------------------------------


@dataclass(frozen=True, slots=True)
class LlmCallSummary:
    """One chat call with its adaptation and repair requests; no content, address or header."""

    purpose: LlmPurpose
    integration_public_id: str | None
    model: str
    started_at: datetime
    wait_ms: int
    duration_ms: int
    outcome: LlmOutcome
    http_status: int | None
    requests: int
    adaptations: tuple[AdaptedFeature, ...]
    repaired: bool
    prompt_tokens: int
    completion_tokens: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready form for the analysis record (analysis-records owns its storage)."""

        return {
            "purpose": self.purpose.value,
            "integration_public_id": self.integration_public_id,
            "model": self.model,
            "started_at": self.started_at.isoformat(),
            "wait_ms": self.wait_ms,
            "duration_ms": self.duration_ms,
            "outcome": self.outcome.value,
            "http_status": self.http_status,
            "requests": self.requests,
            "adaptations": [feature.value for feature in self.adaptations],
            "repaired": self.repaired,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


@dataclass(frozen=True, slots=True)
class LlmChatRequest:
    """System prompt, user content, JSON schema and token budget of one chat call."""

    system: str = field(repr=False)
    user: str = field(repr=False)
    schema: Mapping[str, Any] = field(repr=False)
    max_tokens: int
    purpose: LlmPurpose
    # Written into the llm.call log event when the caller is an analysis.
    analysis_public_id: str | None = None


@dataclass(frozen=True, slots=True)
class LlmChatResult:
    """The parsed JSON object, or the failure class; the summary in every case."""

    outcome: LlmOutcome
    summary: LlmCallSummary
    value: dict[str, Any] | None = field(default=None, repr=False)
    http_status: int | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is LlmOutcome.OK


@dataclass(frozen=True, slots=True)
class LlmProbeResult:
    """A ``/models`` read: outcome class, HTTP status, duration and whether it came from cache."""

    operation: ProbeOperation
    outcome: LlmOutcome
    http_status: int | None
    duration_ms: int
    cached: bool = False

    @property
    def ok(self) -> bool:
        return self.outcome is LlmOutcome.OK

    @property
    def message(self) -> str:
        return probe_message(self.outcome, self.http_status)


@dataclass(frozen=True, slots=True)
class LlmModelInfo:
    """What a server tells about one model (Requirement 14); ``in_use`` is added by the caller."""

    id: str
    type: str
    loaded: bool | None
    context: int | None
    owner: str
    quant: str


@dataclass(frozen=True, slots=True)
class LlmModelList:
    probe: LlmProbeResult
    models: tuple[LlmModelInfo, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelState:
    """Requirement 12: what the main screen and the administration shell show about the model."""

    state: Literal["ok", "none", "down"]
    model: str
    code: LlmOutcome | None
    reason: str

    @classmethod
    def not_configured(cls) -> "ModelState":
        return cls(
            state="none",
            model="",
            code=LlmOutcome.NOT_CONFIGURED,
            reason=short_reason(LlmOutcome.NOT_CONFIGURED, probe=True),
        )

    @classmethod
    def from_probe(cls, model: str, probe: LlmProbeResult) -> "ModelState":
        if probe.ok:
            return cls(state="ok", model=model, code=None, reason="")
        return cls(state="down", model=model, code=probe.outcome, reason=probe.message)


# --- Decision 1: the model port -----------------------------------------------------------------


class CancelSignal(Protocol):
    """A stop request of an analysis; the source's ``cancel.Token`` has this shape."""

    @property
    def cancelled(self) -> bool: ...

    def on_cancel(self, hook: Callable[[], None]) -> Callable[[], None]:
        """Run ``hook`` when cancelled (at once when already cancelled); returns an unregister."""
        ...


class LlmChatPort(Protocol):
    """The only way to the model server (Decision 1)."""

    async def chat(
        self,
        connection: LlmConnection,
        request: LlmChatRequest,
        *,
        cancel: CancelSignal | None = None,
    ) -> LlmChatResult:
        """One chat call with its adaptations and repair; a stop ends it as ``cancelled``."""
        ...

    async def health(self, connection: LlmConnection) -> LlmProbeResult:
        """``GET /models`` within 5 s, shared for 30 s per connection (Requirement 12)."""
        ...

    async def list_models(
        self,
        connection: LlmConnection,
        *,
        operation: ProbeOperation = ProbeOperation.MODELS,
        details: bool = True,
    ) -> LlmModelList:
        """The server's models; ``details`` adds LM Studio's detail list (Requirement 14)."""
        ...
