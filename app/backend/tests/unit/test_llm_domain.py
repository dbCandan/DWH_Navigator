"""Model connection rules without a server (data-dictionary 003-llm-connection).

Requirement 1 constants, Requirement 2 field rules and messages, address normalization and origin,
the environment's scheme rule, Requirement 7 rule order, Requirement 8 parsing (the source's
``tests/test_llm.py`` examples), Requirement 13 texts and the Turkish folding.
"""

from typing import Any

import pytest

from app.core import telemetry
from app.domain import llm
from app.domain.llm import (
    AdaptedFeature,
    LlmConnection,
    LlmIntegrationInvalid,
    LlmOutcome,
    LlmPurpose,
    ModelState,
    ProbeOperation,
    check_integration_fields,
    context_exceeded,
    endpoint_origin,
    endpoint_problem,
    endpoint_url,
    lm_studio_models_url,
    normalize_endpoint,
    parse_json_reply,
    probe_message,
    refused_feature,
    short_reason,
)
from app.domain.turkish_text import fold
from app.infrastructure.llm.openai_adapter import LlmTimeouts

pytestmark = pytest.mark.unit

SPARK = "http://10.0.0.5:8000/v1"


def _fields(**overrides: Any) -> llm.IntegrationFields:
    values: dict[str, Any] = {
        "name": "DGX Spark 1",
        "endpoint": SPARK,
        "chat_model": "gemma",
        "temperature": 0.0,
        "timeout_seconds": 900,
        "reasoning_effort": "none",
        "seed": 42,
        "api_key": None,
        "environment": "local",
    }
    values.update(overrides)
    return check_integration_fields(**values)


def _problems(**overrides: Any) -> list[str]:
    with pytest.raises(LlmIntegrationInvalid) as raised:
        _fields(**overrides)
    return list(raised.value.problems)


def test_fixed_values_are_the_prd_constants() -> None:
    assert llm.USER_AGENT == "DWHNavigator-Backend/1.0 (internal data dictionary; httpx)"
    assert llm.MAX_RESPONSE_BYTES == 4 * 1024 * 1024
    assert (llm.MAX_ADAPTATIONS, llm.MAX_REPLIES, llm.MAX_INTEGRATIONS) == (3, 2, 50)
    assert (llm.ERROR_TEXT_CHARS, llm.REPAIR_REPLY_CHARS, llm.INVENTORY_PARALLEL) == (600, 2000, 8)
    timeouts = LlmTimeouts()
    assert (timeouts.connect, timeouts.health, timeouts.health_ttl) == (10, 5, 30)
    assert (timeouts.model_list, timeouts.model_list_budget, timeouts.lm_studio) == (10, 10, 3)
    assert (timeouts.inventory, timeouts.inventory_server_budget) == (6, 10)
    assert (timeouts.inventory_budget, timeouts.test_chat, timeouts.test_chat_budget) == (
        50,
        30,
        30,
    )
    # Requirement 9: the test's ceiling is its server step (10 s) and its chat step (30 s).
    assert llm.TEST_SERVER_BUDGET_SECONDS + llm.TEST_CHAT_BUDGET_SECONDS == 40


def test_the_telemetry_label_sets_are_the_domain_values() -> None:
    assert telemetry.LLM_OUTCOMES == {outcome.value for outcome in LlmOutcome}
    assert telemetry.LLM_PURPOSES == {purpose.value for purpose in LlmPurpose}
    assert telemetry.LLM_PROBE_OPERATIONS == {operation.value for operation in ProbeOperation}
    assert telemetry.LLM_FEATURES == {feature.value for feature in AdaptedFeature}
    assert telemetry.LLM_TOKEN_KINDS == {"prompt", "completion"}
    assert len(LlmOutcome) == 17  # ok and the 16 classes of Requirement 13


def test_addresses_are_normalized_as_in_the_source() -> None:
    assert normalize_endpoint(" http://h:8000/v1/chat/completions/ ") == "http://h:8000/v1"
    assert normalize_endpoint("http://h/v1/models") == "http://h/v1"
    assert normalize_endpoint("http://h/v1///") == "http://h/v1"
    assert endpoint_url("http://h:8000/v1", "/chat/completions") == (
        "http://h:8000/v1/chat/completions"
    )
    assert lm_studio_models_url("http://h:1234/v1") == "http://h:1234/api/v0/models"
    assert lm_studio_models_url("http://h:1234/openai") is None


def test_the_origin_is_scheme_host_and_port() -> None:
    assert endpoint_origin("http://LLM.corp:8000/v1") == "http://llm.corp:8000"
    assert endpoint_origin("https://llm.corp/v1") == "https://llm.corp:443"
    assert endpoint_origin("http://llm.corp/v1") == "http://llm.corp:80"
    assert endpoint_origin("http://[fd00::5]:8000/v1") == "http://[fd00::5]:8000"
    assert endpoint_origin("https://llm.corp/v1") != endpoint_origin("https://llm.corp:8443/v1")


def test_valid_fields_are_trimmed_and_defaults_kept() -> None:
    fields = _fields(name="  DGX Spark 1 ", endpoint=f" {SPARK}/models ", chat_model=" gemma ")
    assert (fields.name, fields.endpoint, fields.chat_model) == ("DGX Spark 1", SPARK, "gemma")
    assert (fields.temperature, fields.timeout_seconds, fields.reasoning_effort, fields.seed) == (
        0.0,
        900,
        "none",
        42,
    )
    numeric_text = _fields(temperature="0.5", timeout_seconds="120", seed="-1")
    assert (numeric_text.temperature, numeric_text.timeout_seconds, numeric_text.seed) == (
        0.5,
        120,
        -1,
    )
    assert _fields(reasoning_effort="").reasoning_effort == ""
    assert _fields(timeout_seconds=60.0).timeout_seconds == 60


def test_source_messages_are_kept_and_joined() -> None:
    problems = _problems(
        name=" ",
        endpoint="10.0.0.5:8000",
        temperature=3,
        timeout_seconds=4,
        reasoning_effort="max",
    )
    assert problems == [
        "Ad boş olamaz",
        (
            "API adresi http:// veya https:// ile başlayan tam bir adres olmalı "
            "(ör. http://10.0.0.5:8000/v1)"
        ),
        "Sıcaklık 0 ile 2 arasında olmalı",
        "Zaman aşımı 5 ile 3600 saniye arasında olmalı",
        "Düşünme modu geçersiz",
    ]
    assert LlmIntegrationInvalid(problems).message == "; ".join(problems)


@pytest.mark.parametrize(
    "overrides",
    [{"temperature": "sıcak"}, {"timeout_seconds": "12.5"}, {"seed": 1.5}, {"temperature": True}],
)
def test_a_value_that_is_not_a_number_answers_alone(overrides: dict[str, Any]) -> None:
    assert _problems(name="", **overrides) == ["Sayısal alanlardan biri geçersiz"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "x" * 101}, "Ad en çok 100 karakter olabilir"),
        ({"endpoint": "http://h/" + "a" * 2048}, "API adresi en çok 2048 karakter olabilir"),
        ({"chat_model": "m" * 257}, "Sohbet modeli en çok 256 karakter olabilir"),
        ({"api_key": "k" * 4097}, "API anahtarı en çok 4096 karakter olabilir"),
        ({"seed": 2147483648}, "Seed -1 ile 2147483647 arasında olmalı"),
        ({"seed": -2}, "Seed -1 ile 2147483647 arasında olmalı"),
        ({"api_key": "gizli anahtar"}, "API anahtarı geçersiz karakter içeriyor"),
        ({"api_key": "gizli\x00"}, "API anahtarı geçersiz karakter içeriyor"),
        ({"name": "ad\x07"}, "Ad geçersiz karakter içeriyor"),
        ({"chat_model": "m\x1b"}, "Sohbet modeli geçersiz karakter içeriyor"),
    ],
)
def test_new_limits_have_their_messages(overrides: dict[str, Any], message: str) -> None:
    problems = _problems(**overrides)
    assert problems == [message]
    for value in overrides.values():
        if isinstance(value, str) and len(value) < 50:
            assert value not in "; ".join(problems)  # no submitted value is echoed


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://kullanici:parola@10.0.0.5/v1",
        "http://10.0.0.5/v1?x=1",
        "http://10.0.0.5/v1#parca",
        "http://@10.0.0.5/v1",
    ],
)
def test_credentials_queries_and_fragments_are_refused(endpoint: str) -> None:
    assert endpoint_problem(endpoint, "local") == (
        "API adresi kullanıcı adı, parola, sorgu veya # parçası içeremez"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "ftp://10.0.0.5/v1",
        "http://",
        "http://:8000/v1",
        "http://h:0/v1",
        "http://h:99999/v1",
        "http://h /v1",
        "http://h/v\t1",
    ],
)
def test_malformed_addresses_get_the_source_message(endpoint: str) -> None:
    assert endpoint_problem(endpoint, "local") == (
        "API adresi http:// veya https:// ile başlayan tam bir adres olmalı "
        "(ör. http://10.0.0.5:8000/v1)"
    )


def test_nonprod_accepts_only_https() -> None:
    assert endpoint_problem(SPARK, "local") is None
    assert endpoint_problem(SPARK, "nonprod") == "Bu ortamda API adresi https:// ile başlamalı"
    assert endpoint_problem("https://runai.corp.example/inference/m/v1", "nonprod") is None


def test_rule_order_and_still_sent_features() -> None:
    every = {"system_role": True, "structured": True, "reasoning_effort": "none", "seed": 42}
    text = fold("HTTP 400: DEVELOPER INSTRUCTION is not enabled; schema; reasoning; seed")
    assert refused_feature(text, **every) is AdaptedFeature.SYSTEM_ROLE
    assert refused_feature(text, **{**every, "system_role": False}) is (
        AdaptedFeature.RESPONSE_FORMAT
    )
    assert refused_feature(text, **{**every, "system_role": False, "structured": False}) is (
        AdaptedFeature.REASONING_EFFORT
    )
    no_effort = {**every, "system_role": False, "structured": False, "reasoning_effort": ""}
    assert refused_feature(text, **no_effort) is AdaptedFeature.SEED
    assert refused_feature(text, **{**no_effort, "seed": None}) is None
    assert refused_feature(fold("response_mime_type is unknown"), **every) is (
        AdaptedFeature.RESPONSE_FORMAT
    )
    assert refused_feature(fold("Thinking is not supported"), **every) is (
        AdaptedFeature.REASONING_EFFORT
    )
    assert refused_feature(fold("bilinmeyen alan"), **every) is None


def test_the_thinking_switch_rule() -> None:
    sent = {
        "system_role": False,
        "structured": True,
        "reasoning_effort": "",
        "seed": 42,
        "thinking_off": True,
    }
    for text in (
        "chat_template_kwargs is not supported",
        "unexpected keyword enable_thinking",
        "Chat TEMPLATE rejected the arguments",
    ):
        assert refused_feature(fold(text), **sent) is AdaptedFeature.CHAT_TEMPLATE_KWARGS
        # Not sent, never refused.
        assert refused_feature(fold(text), **{**sent, "thinking_off": False}) is None
    # The system role and schema rules keep their precedence.
    both = fold("chat_template_kwargs: schema and seed are not supported")
    assert refused_feature(both, **sent) is AdaptedFeature.RESPONSE_FORMAT
    # An error that names the switch drops it before the effort and seed rules.
    named = {**sent, "structured": False, "reasoning_effort": "none"}
    assert refused_feature(both, **named) is AdaptedFeature.CHAT_TEMPLATE_KWARGS
    thinking = fold("unexpected keyword enable_thinking")
    assert refused_feature(thinking, **named) is AdaptedFeature.CHAT_TEMPLATE_KWARGS
    # A bare "template" word still comes after the source rules.
    late = fold("template and seed are not supported")
    assert refused_feature(late, **named) is AdaptedFeature.SEED


def test_context_exceeded_needs_context_and_a_size_word() -> None:
    assert context_exceeded(fold("maximum context length is 65536 tokens"))
    assert context_exceeded(fold("request exceeds the CONTEXT window"))
    assert context_exceeded(fold("context size too small"))
    assert not context_exceeded(fold("context missing"))
    assert not context_exceeded(fold("length exceeded"))


class TestParse:
    """The source's tests/test_llm.py examples."""

    def test_plain(self) -> None:
        assert parse_json_reply('{"a": 1}') == {"a": 1}

    def test_fenced_and_thinking(self) -> None:
        text = '<think>hmm</think>\n```json\n{"matches": []}\n```'
        assert parse_json_reply(text) == {"matches": []}

    def test_thought_block_with_draft_json(self) -> None:
        text = '<thought>taslak: `{"secim": 2, "gerekce": "ya`</thought>{"secim": 1}'
        assert parse_json_reply(text) == {"secim": 1}

    def test_prose_around(self) -> None:
        assert parse_json_reply('Tabii: {"x": [1]} umarım yardımcı olur') == {"x": [1]}

    def test_garbage(self) -> None:
        assert parse_json_reply("yok") is None
        assert parse_json_reply("[1, 2]") is None
        assert parse_json_reply('"metin"') is None
        assert parse_json_reply("") is None


def test_short_reasons_and_check_messages() -> None:
    assert short_reason(LlmOutcome.UNAUTHORIZED, 401, probe=True) == (
        "Sunucu HTTP 401 döndürdü (API anahtarı eksik veya geçersiz)"
    )
    assert short_reason(LlmOutcome.UPSTREAM_STATUS, 500, probe=False) == "Sunucu HTTP 500 döndürdü"
    assert short_reason(LlmOutcome.INVALID_RESPONSE, probe=False) == "beklenmeyen yanıt"
    assert short_reason(LlmOutcome.OUTPUT_TRUNCATED, probe=False) == (
        "model cevabı uzunluk sınırında kesildi"
    )
    assert probe_message(LlmOutcome.OUTPUT_TRUNCATED) == "model cevabı uzunluk sınırında kesildi"
    assert short_reason(LlmOutcome.INVALID_RESPONSE, probe=True) == (
        "yanıt JSON değil — adres OpenAI uyumlu API'nin /v1 adresi mi?"
    )
    assert probe_message(LlmOutcome.CONNECT_REFUSED) == (
        "Model sunucusuna ulaşılamadı: bağlantı reddedildi — adres/port yanlış ya da sunucu kapalı"
    )
    assert probe_message(LlmOutcome.INVALID_RESPONSE).startswith("Model sunucusuna ulaşılamadı: ")
    assert probe_message(LlmOutcome.UNAUTHORIZED, 403) == (
        "Sunucu HTTP 403 döndürdü (API anahtarı eksik veya geçersiz)"
    )
    assert probe_message(LlmOutcome.KEY_UNREADABLE) == (
        "Kayıtlı API anahtarı okunamadı; anahtarı yeniden girin"
    )
    unreachable = {
        LlmOutcome.NETWORK_POLICY_DENIED,
        LlmOutcome.NAME_UNRESOLVED,
        LlmOutcome.CONNECT_REFUSED,
        LlmOutcome.CONNECT_ERROR,
        LlmOutcome.TLS_ERROR,
        LlmOutcome.TIMEOUT,
        LlmOutcome.INVALID_RESPONSE,
    }
    for outcome in LlmOutcome:
        if outcome is LlmOutcome.OK:
            continue
        message = probe_message(outcome, 500)
        assert message.startswith("Model sunucusuna ulaşılamadı: ") == (outcome in unreachable)
        assert "http://" not in message and "10.0.0.5" not in message


def test_model_state_objects() -> None:
    none = ModelState.not_configured()
    assert (none.state, none.model, none.code, none.reason) == (
        "none",
        "",
        LlmOutcome.NOT_CONFIGURED,
        "Sohbet modeli bağlı değil",
    )


def test_turkish_folding_is_the_source_fold() -> None:
    assert fold("İSTANBUL Işık ÇAĞRI ŞÖĞÜÂÎÛ éèä") == "istanbul isik cagri soguaiu eea"
    assert fold("DEVELOPER INSTRUCTION") == "developer instruction"


def test_the_fingerprint_follows_every_connection_field() -> None:
    secret = "gizli-anahtar-placeholder"
    base = LlmConnection(endpoint=SPARK, chat_model="m", api_key="k", public_id="p")
    assert secret not in repr(LlmConnection(endpoint=SPARK, api_key=secret))
    variants = [
        LlmConnection(endpoint=SPARK + "x", chat_model="m", api_key="k", public_id="p"),
        LlmConnection(endpoint=SPARK, chat_model="n", api_key="k", public_id="p"),
        LlmConnection(endpoint=SPARK, chat_model="m", api_key="l", public_id="p"),
        LlmConnection(endpoint=SPARK, chat_model="m", api_key="k", temperature=0.1, public_id="p"),
        LlmConnection(endpoint=SPARK, chat_model="m", api_key="k", timeout_seconds=60),
        LlmConnection(endpoint=SPARK, chat_model="m", api_key="k", reasoning_effort=""),
        LlmConnection(endpoint=SPARK, chat_model="m", api_key="k", seed=-1),
    ]
    assert len({base.fingerprint, *(v.fingerprint for v in variants)}) == len(variants) + 1
    assert base.sampling == ("m", 0.0, "none", 42)
