"""How the LLM call log writes a body down."""

import json

from app.domain.llm_call_log import MAX_BODY_CHARS, SECRET_MASK, readable_body


def test_json_keeps_its_turkish_letters() -> None:
    raw = json.dumps({"content": "Şube müşterisi"}).encode()
    assert b"\\u015e" in raw
    assert readable_body(raw, None) == ('{"content": "Şube müşterisi"}', False)


def test_the_api_key_is_cut_out_of_the_body() -> None:
    text, _ = readable_body(b'{"error": "bad key gizli-anahtar"}', "gizli-anahtar")
    assert "gizli-anahtar" not in text
    assert SECRET_MASK in text


def test_a_body_that_is_not_json_stays_text_without_nul() -> None:
    assert readable_body(b"<html>\x00502\xff</html>", None) == ("<html>502�</html>", False)


def test_an_escaped_nul_in_json_stays_escaped() -> None:
    assert readable_body(b'{"a": "x\\u0000y"}', None) == ('{"a": "x\\u0000y"}', False)


def test_a_lone_surrogate_in_json_can_still_be_stored() -> None:
    text, _ = readable_body(b'{"a": "x\\ud800y"}', None)
    text.encode("utf-8")


def test_a_long_body_is_cut_and_says_so() -> None:
    text, truncated = readable_body(b"x" * (MAX_BODY_CHARS + 1), None)
    assert (len(text), truncated) == (MAX_BODY_CHARS, True)
