"""LLM integrations (ADR-032): roles, activation rules, settings, and the admin page's API
with a fake model server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from vsa.config import LLMSettings, integrations_path, load_settings, read_integrations
from vsa.llm.client import LLMError, OpenAICompatibleClient
from vsa.llm.integrations import (
    Integration,
    apply,
    conflicts,
    from_llm_settings,
    is_internal,
    new_id,
    normalize_endpoint,
    validate,
)
from vsa.pipeline import Engine
from vsa.web.server import App

SPARK = "http://10.0.0.5:8000/v1"


def _it(iid: str, chat: str = "", on: bool = True) -> Integration:
    return Integration(iid, iid, SPARK, chat_model=chat, enabled=on)


def test_endpoint_and_id_helpers() -> None:
    assert normalize_endpoint(" http://h:8000/v1/chat/completions/ ") == "http://h:8000/v1"
    assert normalize_endpoint("http://h/v1/models") == "http://h/v1"
    assert new_id("DGX Spark 1", set()) == "dgx-spark-1"
    assert new_id("DGX Spark 1", {"dgx-spark-1"}) == "dgx-spark-1-2"
    assert new_id("İç Sunucu", set()) == "ic-sunucu"


def test_internal_addresses() -> None:
    for url in ("http://127.0.0.1:1234/v1", "http://10.0.0.5:8000/v1", "http://192.168.1.9/v1",
                "http://spark1:8000/v1", "http://llm.bank.local/v1", "http://localhost:1/v1",
                "http://100.122.111.9:1234/v1"):  # Tailscale / CGNAT space
        assert is_internal(url), url
    assert not is_internal("https://api.openai.com/v1")
    assert not is_internal("https://8.8.8.8/v1")


def test_validation_messages() -> None:
    ok = _it("a", chat="m")
    assert validate(ok, []) == []
    assert validate(Integration("b", "a", SPARK), [ok])  # same name
    assert validate(Integration("c", "c", "10.0.0.5:8000"), [])  # no scheme
    assert validate(Integration("d", " ", SPARK), [])


def test_one_active_chat_holder() -> None:
    chat, other = _it("chat", chat="c"), _it("other", "c2", on=False)
    assert [c.id for c in conflicts([chat, other], other)] == ["chat"]
    assert conflicts([chat], _it("none")) == []  # no role, no conflict


def test_apply_active_integrations_to_llm_settings() -> None:
    llm = LLMSettings(enabled=True, endpoint="http://old/v1", model="old")
    chat = Integration("c", "c", SPARK, api_key="k1", chat_model="gpt", enabled=True,
                       temperature=0.2, timeout=300)  # fmt: skip
    apply(llm, [chat])
    assert (llm.enabled, llm.endpoint, llm.model, llm.api_key) == (True, SPARK, "gpt", "k1")
    assert (llm.temperature, llm.timeout) == (0.2, 300)
    chat.enabled = False
    apply(llm, [chat])
    assert not llm.enabled and llm.model == "" and llm.endpoint == ""


def test_existing_llm_settings_become_an_integration() -> None:
    llm = LLMSettings(enabled=True, endpoint="http://127.0.0.1:1234/v1", model="gpt", api_key="k")
    (it,) = from_llm_settings(llm)
    assert it.enabled and (it.chat_model, it.api_key) == ("gpt", "k")
    assert from_llm_settings(LLMSettings()) == []


def test_load_settings_reads_the_integrations_file(tmp_path: Path) -> None:
    settings = tmp_path / "settings.yaml"
    settings.write_text("llm:\n  enabled: true\n  endpoint: http://old/v1\n  model: old\n",
                        encoding="utf-8")  # fmt: skip
    assert load_settings(settings).llm.model == "old"  # no file: settings.yaml rules
    integrations_path(settings).write_text(
        "integrations:\n- id: s\n  name: S\n  endpoint: http://10.0.0.5:8000/v1\n"
        "  enabled: true\n  chat_model: gpt\n  future_field: 1\n",
        encoding="utf-8",
    )
    llm = load_settings(settings).llm
    assert (llm.enabled, llm.endpoint, llm.model) == (True, SPARK, "gpt")


def test_files_from_before_vector_search_was_removed_still_load(tmp_path: Path) -> None:
    """Old settings carry a ``dense:`` section and embedding fields; old integrations an
    embedding model. All of it is ignored, nothing fails."""
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        "llm:\n  enabled: true\n  endpoint: http://old/v1\n  model: old\n"
        "  embedding_model: bge\n  embedding_endpoint: http://old:8001/v1\n"
        "dense:\n  enabled: true\n  top_k: 150\n  weight: 0.35\n",
        encoding="utf-8",
    )
    assert load_settings(settings).llm.model == "old"
    integrations_path(settings).write_text(
        "integrations:\n- id: s\n  name: S\n  endpoint: http://10.0.0.5:8000/v1\n"
        "  enabled: true\n  chat_model: gpt\n  embedding_model: bge\n"
        "- id: e\n  name: E\n  endpoint: http://10.0.0.6:8001/v1\n"
        "  enabled: true\n  embedding_model: bge\n",
        encoding="utf-8",
    )
    llm = load_settings(settings).llm
    assert (llm.enabled, llm.endpoint, llm.model) == (True, SPARK, "gpt")
    s, e = read_integrations(integrations_path(settings)) or []
    assert s.enabled and s.roles == ["chat"]
    assert not e.enabled and e.roles == []  # embedding-only entry: kept, never active


# --------------------------------------------------------------------------- admin API


class FakeServer:
    """Stands in for one OpenAI-compatible server on every client the admin page makes."""

    blank = {"type": "", "loaded": None, "owner": "", "quant": ""}
    models = [
        {"id": "gpt-oss", "context": 131072, **blank},
        {"id": "qwen3-32b", "context": 32768, **blank},
    ]

    def __init__(self, monkeypatch: pytest.MonkeyPatch, down: bool = False) -> None:
        self.keys: list[str] = []

        def listed(client: OpenAICompatibleClient, timeout: float = 10) -> list[dict[str, Any]]:
            self.keys.append(client.api_key)
            if down:
                raise LLMError("Model sunucusuna ulaşılamadı")
            return [dict(m) for m in self.models]

        monkeypatch.setattr(OpenAICompatibleClient, "list_models", listed)
        monkeypatch.setattr(OpenAICompatibleClient, "ping",
                            lambda c: [m["id"] for m in listed(c)])  # fmt: skip
        monkeypatch.setattr(OpenAICompatibleClient, "chat_json",
                            lambda c, *a, **k: {"cevap": "Ankara"})  # fmt: skip
        monkeypatch.setattr(OpenAICompatibleClient, "health", lambda c: "down" if down else "")


@pytest.fixture
def app(sample_dictionary_path: Path, tmp_path: Path) -> App:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        f"dictionary:\n  path: {sample_dictionary_path.as_posix()}\n"
        f"index:\n  dir: {(tmp_path / 'idx').as_posix()}\n",
        encoding="utf-8",
    )
    s = load_settings(settings_file)
    Engine.from_dictionary_file(s).save()
    return App(Engine.from_index(s), tmp_path / "out", tmp_path / "fb.jsonl", settings_file)


def _form(**kw: Any) -> dict[str, Any]:
    return {"name": "DGX Spark 1", "endpoint": SPARK + "/chat/completions", "api_key": "sk-1",
            "chat_model": "gpt-oss", "temperature": 0, "timeout": 900,
            "reasoning_effort": "none", "seed": 42, **kw}  # fmt: skip


def test_add_activate_and_the_engine_follows(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeServer(monkeypatch)
    llm = app.llm_admin
    assert llm.state()["items"] == [] and not llm.state()["saved"]
    r = llm.save(_form(activate=True))
    assert r["ok"] and r["id"] == "dgx-spark-1"
    item = r["state"]["items"][0]
    assert item["endpoint"] == SPARK and item["enabled"] and item["has_key"]
    assert "api_key" not in item and "sk-1" not in str(r)  # the key never goes back
    assert r["state"]["roles"]["chat"]["model"] == "gpt-oss"
    assert app.engine.llm.available and app.engine.llm.model == "gpt-oss"  # engine rebuilt
    assert read_integrations(llm.path)[0].api_key == "sk-1"  # type: ignore[index]

    llm.save({**_form(), "id": "dgx-spark-1", "api_key": ""})  # blank key = keep
    assert read_integrations(llm.path)[0].api_key == "sk-1"  # type: ignore[index]
    assert llm.set_active({"id": "dgx-spark-1", "enabled": False})["ok"]
    assert not app.engine.llm.available  # passive: the rule pipeline answers


def test_second_chat_holder_needs_replace(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeServer(monkeypatch)
    llm = app.llm_admin
    llm.save(_form(activate=True))
    r = llm.save(_form(name="Spark 2", activate=True))
    assert r["ok"] is False and r["conflict"][0]["name"] == "DGX Spark 1"
    assert len(llm.items()) == 1  # nothing saved on conflict
    r = llm.save(_form(name="Spark 2", activate=True, replace=True))
    on = {i["name"]: i["enabled"] for i in r["state"]["items"]}
    assert on == {"DGX Spark 1": False, "Spark 2": True}
    with pytest.raises(ValueError, match="modeli seçin"):
        llm.save(_form(name="Boş", chat_model=""))
        llm.set_active({"id": "bos", "enabled": True})
    with pytest.raises(KeyError):
        llm.set_active({"id": "yok", "enabled": True})


def test_validation_and_delete(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeServer(monkeypatch)
    llm = app.llm_admin
    with pytest.raises(ValueError, match="API adresi"):
        llm.save(_form(endpoint="10.0.0.5:8000"))
    llm.save(_form(activate=True))
    with pytest.raises(ValueError, match="zaten var"):
        llm.save(_form())
    assert llm.delete({"id": "dgx-spark-1"})["state"]["items"] == []
    assert not app.engine.llm.available


def test_test_models_and_inventory(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    server = FakeServer(monkeypatch)
    llm = app.llm_admin
    llm.save(_form(activate=True))
    r = llm.test({"id": "dgx-spark-1", "record": True})
    names = [s["name"] for s in r["steps"]]
    assert r["ok"] and names == ["Sunucu", "Sohbet modeli"]
    assert "Ankara" in r["steps"][1]["detail"]
    assert server.keys[-1] == "sk-1"  # the stored key is used, the browser never had it
    assert llm.state()["items"][0]["last_test"]["ok"]

    form = llm.test({**_form(api_key="sk-yeni")})  # unsaved form values
    assert form["ok"] and server.keys[-1] == "sk-yeni"

    models = llm.models({"id": "dgx-spark-1"})["models"]
    in_use = {m["id"]: m["in_use"] for m in models}
    assert in_use == {"gpt-oss": ["chat"], "qwen3-32b": []}
    inv = llm.inventory()["servers"]
    assert inv[0]["ok"] and len(inv[0]["models"]) == 2


def test_unreachable_server_is_reported_not_raised(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeServer(monkeypatch, down=True)
    llm = app.llm_admin
    llm.save(_form())
    r = llm.test({"id": "dgx-spark-1"})
    assert not r["ok"] and len(r["steps"]) == 1 and "ulaşılamadı" in r["steps"][0]["detail"]
    assert llm.models({"id": "dgx-spark-1"})["ok"] is False
    assert llm.inventory()["servers"][0]["ok"] is False
