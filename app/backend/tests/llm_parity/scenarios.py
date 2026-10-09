"""Side-by-side scenarios of the source client and the target adapter (003-llm-connection).

Standard library only: the source side imports this module next to the source package. Each
scenario is a connection, the chat calls made on one client in order, and the scripted answers
of the fake server. ``expected`` is the Requirement 13 class of each call on the target.
``thinking_off_from`` declares the one target difference (Requirement 7, rule 3): from that
request on, the target sends ``chat_template_kwargs`` where the source sent nothing, because the
server refused ``reasoning_effort: "none"``. Every other byte stays the source's.
"""

import json
from dataclasses import dataclass, field
from typing import Any

SOURCE_COMMIT = "76e21a3a52264f7d7da4d930100a7c69212e4916"
# Git blob ids of the source files the client imports, at SOURCE_COMMIT.
SOURCE_BLOBS = {
    "src/vsa/__init__.py": "1522c9072ca53ff9a9801ea3ba444b6cbc4337e7",
    "src/vsa/cancel.py": "b9ad9530d64f3a2ce227f9112fe334ce0c2fcf55",
    "src/vsa/llm/__init__.py": "cb54a456f58fc61b204aeb5f5485004f18ff2119",
    "src/vsa/llm/client.py": "eed01d390bd06384b70e1789d6727ad5dc92df8f",
    "src/vsa/text/__init__.py": "7539ebc483e441286ba413d7cd51edd8a71e37d6",
    "src/vsa/text/normalize.py": "73dd647c6eea71bef24f1d6ef03e96dae6bf3236",
    "src/vsa/trace.py": "47147f6f1ceb63a2debefcc9faf1d06d19042c42",
}

Answer = tuple[int, str]

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tablolar": {"type": "array", "items": {"type": "string"}},
        "gerekçe": {"type": "string", "description": "Kısa açıklama; müşteri ve şube"},
    },
    "required": ["tablolar"],
    "additionalProperties": False,
}
TEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"cevap": {"type": "string"}},
    "required": ["cevap"],
    "additionalProperties": False,
}


def reply(content: str, *, prompt_tokens: int = 1200, completion_tokens: int = 40) -> Answer:
    body = {
        "id": "sohbet-1",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }
    return 200, json.dumps(body)


def error(status: int, message: str) -> Answer:
    return status, json.dumps({"error": {"message": message}})


@dataclass(frozen=True)
class Call:
    system: str = "Sen bir veri sözlüğü analistisin. SADECE JSON döndür."
    user: str = "Müşterinin şube bazında İSTANBUL kredi kartı limiti hangi tabloda?"
    schema: dict[str, Any] = field(default_factory=lambda: SCHEMA)
    max_tokens: int = 2500


@dataclass(frozen=True)
class Scenario:
    name: str
    answers: tuple[Answer, ...]
    expected: tuple[str, ...]
    calls: tuple[Call, ...] = (Call(),)
    model: str = "gemma-4-31b"
    temperature: float = 0.0
    reasoning_effort: str = "none"
    seed: int = 42
    api_key: str = ""
    thinking_off_from: int | None = None


_DEVELOPER = "Developer instruction is not enabled for model"
_JSON_MODE = "JSON mode is not enabled for model"
_REASONING = "reasoning_effort is not supported"
_SEED = "unsupported parameter: seed"
_CONTEXT = (
    "This model's maximum context length is 65536 tokens; the request (70212 tokens) exceeds "
    "the context size"
)
_OK = '{"tablolar": ["DWH.KART_LIMIT"]}'

SCENARIOS: tuple[Scenario, ...] = (
    Scenario("duz_yanit", (reply(_OK),), ("ok",)),
    Scenario(
        "kod_citli_ve_think",
        (reply('<think>hmm</think>\n```json\n{"tablolar": []}\n```'),),
        ("ok",),
    ),
    Scenario(
        "thought_blogu",
        (reply('<thought>taslak: `{"secim": 2, "gerekce": "ya`</thought>{"secim": 1}'),),
        ("ok",),
    ),
    Scenario("sistem_reddi", (error(400, _DEVELOPER), reply(_OK)), ("ok",)),
    Scenario("sema_reddi", (error(400, _JSON_MODE), reply(_OK)), ("ok",)),
    Scenario("dusunme_reddi", (error(400, _REASONING), reply(_OK)), ("ok",), thinking_off_from=1),
    Scenario("seed_reddi", (error(400, _SEED), reply(_OK)), ("ok",)),
    Scenario(
        "art_arda_ret_ve_hafiza",
        (
            error(400, _DEVELOPER),
            error(400, _JSON_MODE),
            error(400, _REASONING),
            reply(_OK),
            reply('{"tablolar": ["DWH.SUBE"]}'),
        ),
        ("ok", "ok"),
        calls=(Call(), Call(user="İkinci soru: şube müdürü kim?", max_tokens=8000)),
        thinking_off_from=3,
    ),
    Scenario(
        "dort_ret_siniri",
        (
            error(400, _DEVELOPER),
            error(400, _JSON_MODE),
            error(400, _REASONING),
            error(400, _SEED),
        ),
        ("upstream_status",),
        thinking_off_from=3,
    ),
    Scenario(
        "json_olmayan_ve_onarim",
        (reply("Tabii, cevap şu: tablo yok"), reply(_OK)),
        ("ok",),
    ),
    Scenario(
        "iki_kez_json_olmayan",
        (reply("düz metin"), reply("yine düz metin")),
        ("invalid_json",),
    ),
    Scenario(
        "choices_yok", ((200, '{"id": "x", "object": "chat.completion"}'),), ("invalid_response",)
    ),
    Scenario("dizi_yanit", ((200, "[1, 2]"),), ("invalid_response",)),
    Scenario("yetkisiz_401", (error(401, "invalid api key"),), ("unauthorized",)),
    Scenario("sunucu_500", (error(500, "internal server error"),), ("upstream_status",)),
    Scenario("gecit_504", (error(504, "upstream timed out"),), ("upstream_status",)),
    Scenario("baglam_asimi_400", (error(400, _CONTEXT),), ("context_exceeded",)),
    Scenario(
        "seed_eksi_bir_ve_bos_dusunme",
        (reply(_OK),),
        ("ok",),
        seed=-1,
        reasoning_effort="",
    ),
    Scenario(
        "turkce_icerik_sicaklik_ve_uzun_onarim",
        (reply("Şöyle düşündüm: " + "ğüşıöç İ " * 400), reply(_OK)),
        ("ok",),
        calls=(Call(system="Türkçe sistem istemi: ĞÜŞİÖÇ ğüşıöç “tırnak”", user="Işık ve İğne"),),
        temperature=0.7,
        reasoning_effort="low",
        seed=7,
    ),
    Scenario(
        "baglanti_testi",
        (reply('{"cevap": "Ankara"}', prompt_tokens=30, completion_tokens=5),),
        ("ok",),
        calls=(
            Call(
                system="Kısa ve doğru cevap ver. SADECE JSON döndür.",
                user="Türkiye'nin başkenti neresidir?",
                schema=TEST_SCHEMA,
                max_tokens=60,
            ),
        ),
    ),
    Scenario("anahtarli", (reply(_OK),), ("ok",), api_key="k-parite-123"),
    Scenario(
        "ret_sonra_onarim",
        (error(400, _SEED), reply("JSON değil"), reply(_OK)),
        ("ok",),
    ),
    Scenario(
        "onarimda_ret",
        (reply("JSON değil"), error(400, _JSON_MODE), reply(_OK)),
        ("ok",),
    ),
)
