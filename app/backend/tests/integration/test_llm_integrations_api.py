"""The AI page's endpoints against PostgreSQL and a real-TCP fake model server.

data-dictionary/PRDs/003-llm-connection Requirement 2-5, 12, 14-16, 18, 20-22 (Acceptance 1 and 4):
roles, field rules, the single active chat model under concurrency, the encrypted and
origin-bound key, soft deletion, model lists, the inventory, the connection test, the model state
and the next analysis using a new connection without a restart. No API key, ciphertext or server
text reaches a response or a log.
"""

import asyncio
import base64
import logging
import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.api.llm_integrations.router import get_llm_adapter
from app.db.session import async_session_factory
from app.domain.llm import LlmChatRequest, LlmConnection, LlmOutcome, LlmPurpose
from app.infrastructure.llm.openai_adapter import LlmTimeouts, OpenAICompatibleAdapter
from app.main import app
from app.services.llm_connections import ConnectionKeys, LlmGateway
from tests.fakes.llm_server import (
    FakeLlmServer,
    RecordedRequest,
    Writer,
    chat_reply,
    json_response,
    models_reply,
)
from tests.integration.conftest import AuthHarness, RecordingHandler, SignedIn

pytestmark = pytest.mark.integration

PUBLIC_NAME = "genel.model.example"
MISSING_NAME = "yok.model.example"
FAST = LlmTimeouts(
    connect=2.0,
    health=1.0,
    model_list=1.0,
    model_list_budget=1.5,
    lm_studio=0.3,
    inventory=1.0,
    inventory_server_budget=1.5,
    inventory_budget=3.0,
    test_chat=1.5,
    test_chat_budget=2.0,
)


async def fake_resolver(host: str, port: int) -> list[str]:
    if host == PUBLIC_NAME:
        return ["93.184.216.34"]
    if host == MISSING_NAME:
        raise OSError("not known")
    return ["127.0.0.1"]


def new_key() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def _error(response: Any) -> tuple[int, str]:
    return int(response.status_code), str(response.json()["detail"]["code"])


async def _sql(statement: str, **params: Any) -> list[Any]:
    async with async_session_factory() as session:
        result = await session.execute(text(statement), params)
        rows = list(result.all()) if result.returns_rows else []
        await session.commit()
    return rows


class ModelServer:
    """A plain-HTTP fake model server answering /models and /chat/completions."""

    def __init__(self, server: FakeLlmServer, models: tuple[str, ...]) -> None:
        self.fake = server
        self.models = models
        self.reply = '{"cevap": "Ankara"}'
        server.scenario = self._answer

    async def _answer(self, request: RecordedRequest, reader: Any, writer: Writer) -> None:
        if request.method == "GET" and request.path.endswith("/models"):
            writer.write(models_reply(*self.models))
        elif request.method == "POST":
            writer.write(chat_reply(self.reply))
        else:
            writer.write(json_response({"error": "yok"}, 404))
        await writer.drain()

    @property
    def endpoint(self) -> str:
        return self.fake.url()

    @property
    def requests(self) -> list[RecordedRequest]:
        return self.fake.requests


@dataclass
class Llm:
    auth: AuthHarness
    admin: SignedIn
    manager: SignedIn
    server: ModelServer
    adapter: OpenAICompatibleAdapter

    @property
    def url(self) -> str:
        return f"{self.auth.prefix}/llm-integrations"

    def headers(self, who: SignedIn | None = None) -> dict[str, str]:
        return self.auth.headers(who or self.manager)

    async def get(self, path: str = "", who: SignedIn | None = None) -> Any:
        return await self.auth.client.get(self.url + path, headers=self.headers(who))

    async def post(self, path: str, body: dict[str, Any], who: SignedIn | None = None) -> Any:
        return await self.auth.client.post(self.url + path, json=body, headers=self.headers(who))

    async def put(self, path: str, body: dict[str, Any], who: SignedIn | None = None) -> Any:
        return await self.auth.client.put(self.url + path, json=body, headers=self.headers(who))

    async def delete(self, path: str, who: SignedIn | None = None) -> Any:
        return await self.auth.client.delete(self.url + path, headers=self.headers(who))

    async def create(self, **body: Any) -> dict[str, Any]:
        payload = {"name": f"Sunucu {uuid4().hex[:8]}", "endpoint": self.server.endpoint, **body}
        response = await self.post("", payload)
        assert response.status_code == 201, response.text
        item: dict[str, Any] = response.json()["item"]
        return item

    def use(self, **updates: Any) -> None:
        self.auth.use_settings(**updates)


@pytest.fixture
async def llm(auth: AuthHarness) -> AsyncIterator[Llm]:
    await _sql("DELETE FROM llm_integration")
    auth.use_settings(environment="development", settings_encryption_key=SecretStr(new_key()))
    adapter = OpenAICompatibleAdapter(
        ca_bundle="", max_concurrent_calls=2, resolver=fake_resolver, timeouts=FAST
    )
    app.dependency_overrides[get_llm_adapter] = lambda: adapter
    fake = await FakeLlmServer().start()
    try:
        admin = await auth.super_admin()
        manager = await auth.account(admin, "yonetici")
        yield Llm(auth, admin, manager, ModelServer(fake, ("gemma-4-31b", "qwen")), adapter)
    finally:
        app.dependency_overrides.pop(get_llm_adapter, None)
        await fake.close()


@pytest.fixture
def llm_logs(recorded_logs: RecordingHandler) -> Iterator[RecordingHandler]:
    logger = logging.getLogger("app.llm")
    level = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield recorded_logs
    finally:
        logger.setLevel(level)


# --- Requirement 21: who may use the page -------------------------------------------------------


async def test_every_endpoint_needs_a_session_and_the_manager_role(llm: Llm) -> None:
    user = await llm.auth.account(llm.admin, "kullanici")
    item = await llm.create()
    target = f"/{item['public_id']}"
    calls = [
        ("GET", "", None),
        ("POST", "", {"name": "x", "endpoint": llm.server.endpoint}),
        ("PUT", target, {"name": "y"}),
        ("PUT", f"{target}/active", {"active": False}),
        ("DELETE", target, None),
        ("POST", "/models", {"public_id": item["public_id"]}),
        ("GET", "/inventory", None),
        ("POST", "/test", {"public_id": item["public_id"]}),
    ]
    client = llm.auth.client
    for method, path, body in calls:
        anonymous = await client.request(
            method,
            llm.url + path,
            json=body,
            headers={llm.auth.settings.tenant_header: llm.manager.tenant_id},
        )
        assert _error(anonymous) == (401, "not_authenticated"), (method, path)
        refused = await client.request(method, llm.url + path, json=body, headers=llm.headers(user))
        assert _error(refused) == (403, "forbidden"), (method, path)
    assert (await llm.get(who=llm.admin)).status_code == 200
    assert (await llm.get()).status_code == 200


async def test_a_demoted_manager_is_refused_by_the_service_too(llm: Llm) -> None:
    await _sql(
        "UPDATE app_user_role SET role_id = (SELECT role_id FROM app_role WHERE code = "
        "'kullanici') WHERE user_id = (SELECT user_id FROM app_user WHERE public_id = :p)",
        p=llm.manager.public_id,
    )
    # The token still says yonetici; the service re-reads the account.
    assert _error(await llm.get()) == (403, "forbidden")


# --- Requirement 2 and 3: saving ----------------------------------------------------------------


async def test_creation_defaults_and_the_listing(llm: Llm, llm_logs: RecordingHandler) -> None:
    response = await llm.post(
        "", {"name": "  DGX Spark 1 ", "endpoint": f" {llm.server.endpoint}/chat/completions/ "}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    item = body["item"]
    assert item["name"] == "DGX Spark 1" and item["endpoint"] == llm.server.endpoint
    assert (item["active"], item["has_key"], item["chat_model"], item["last_test"]) == (
        False,
        False,
        "",
        None,
    )
    assert (
        item["temperature"],
        item["timeout_seconds"],
        item["reasoning_effort"],
        item["seed"],
    ) == (
        0.0,
        900,
        "none",
        42,
    )
    assert body["total"] == 1 and body["active"] is None
    assert body["model_state"] == {
        "state": "none",
        "model": "",
        "code": "not_configured",
        "reason": "Sohbet modeli bağlı değil",
        "name": None,
    }
    assert (body["environment"], body["accepts_http"], body["key_storage"]) == ("local", True, True)
    second = await llm.create(name="İkinci")
    listing = (await llm.get()).json()
    assert [entry["public_id"] for entry in listing["items"]] == [
        item["public_id"],
        second["public_id"],
    ]
    (event,) = [e for e in llm_logs.events("llm_integration.changed") if e["action"] == "created"][
        :1
    ]
    assert event["integration_public_id"] == item["public_id"]
    assert event["actor_public_id"] == llm.manager.public_id
    assert "DGX" not in llm_logs.rendered()


async def test_field_errors_are_joined_and_never_echoed(llm: Llm) -> None:
    secret = f"gizli {uuid4().hex}"
    response = await llm.post(
        "",
        {
            "name": " ",
            "endpoint": "10.0.0.5:8000",
            "temperature": 3,
            "timeout_seconds": 4,
            "reasoning_effort": "max",
            "api_key": secret,
        },
    )
    assert _error(response) == (422, "llm_integration_invalid")
    problems = [
        "Ad boş olamaz",
        (
            "API adresi http:// veya https:// ile başlayan tam bir adres olmalı "
            "(ör. http://10.0.0.5:8000/v1)"
        ),
        "Sıcaklık 0 ile 2 arasında olmalı",
        "Zaman aşımı 5 ile 3600 saniye arasında olmalı",
        "Düşünme modu geçersiz",
        "API anahtarı geçersiz karakter içeriyor",
    ]
    assert response.json()["detail"]["message"] == "; ".join(problems)
    assert secret not in response.text
    numeric = await llm.post("", {"name": "a", "endpoint": llm.server.endpoint, "seed": "kırk"})
    assert numeric.json()["detail"] == {
        "code": "llm_integration_invalid",
        "message": "Sayısal alanlardan biri geçersiz",
    }
    unknown = await llm.post("", {"name": "a", "endpoint": llm.server.endpoint, "timeout": 5})
    assert _error(unknown) == (422, "invalid_request")
    broken = await llm.auth.client.post(
        llm.url, content=b"{bozuk", headers={**llm.headers(), "content-type": "application/json"}
    )
    assert _error(broken) == (422, "invalid_request")


async def test_names_are_unique_with_turkish_folding(llm: Llm) -> None:
    first = await llm.create(name="İç Sunucu")
    taken = await llm.post("", {"name": "ic sunucu", "endpoint": llm.server.endpoint})
    assert _error(taken) == (409, "llm_integration_name_taken")
    assert taken.json()["detail"]["message"] == "“ic sunucu” adında bir entegrasyon zaten var"
    other = await llm.create(name="Başka")
    renamed = await llm.put(f"/{other['public_id']}", {"name": "IÇ SUNUCU"})
    assert _error(renamed) == (409, "llm_integration_name_taken")
    assert (await llm.delete(f"/{first['public_id']}")).status_code == 200
    assert (await llm.put(f"/{other['public_id']}", {"name": "İç sunucu"})).status_code == 200


async def test_two_parallel_creations_with_one_name_create_one(llm: Llm) -> None:
    body = {"name": "Yarış", "endpoint": llm.server.endpoint}
    responses = await asyncio.gather(llm.post("", body), llm.post("", body))
    assert sorted(response.status_code for response in responses) == [201, 409]
    rows = await _sql("SELECT count(*) FROM llm_integration WHERE name_key = 'yaris'")
    assert rows[0][0] == 1


async def test_at_most_fifty_integrations(llm: Llm) -> None:
    await _sql(
        "INSERT INTO llm_integration (public_id, tenant_id, name, name_key, endpoint) "
        "SELECT gen_random_uuid()::text, tenant_id, 'n' || g, 'n' || g, :endpoint "
        "FROM tenant, generate_series(1, 50) g WHERE code = 'platform'",
        endpoint=llm.server.endpoint,
    )
    response = await llm.post("", {"name": "elli bir", "endpoint": llm.server.endpoint})
    assert _error(response) == (409, "llm_integration_limit")
    assert response.json()["detail"]["message"] == "En çok 50 entegrasyon tanımlanabilir."


async def test_only_resolvable_private_addresses_are_saved(llm: Llm) -> None:
    public = await llm.post("", {"name": "a", "endpoint": f"http://{PUBLIC_NAME}:8000/v1"})
    assert _error(public) == (422, "llm_endpoint_not_private")
    assert public.json()["detail"]["message"] == (
        "Adres kurum ağı dışında; yalnız kurum içi model sunucusu bağlanabilir."
    )
    literal = await llm.post("", {"name": "b", "endpoint": "http://8.8.8.8/v1"})
    assert _error(literal) == (422, "llm_endpoint_not_private")
    missing = await llm.post("", {"name": "c", "endpoint": f"http://{MISSING_NAME}/v1"})
    assert _error(missing) == (422, "llm_endpoint_unresolved")
    assert missing.json()["detail"]["message"] == "sunucu adı çözülemedi — adresi kontrol edin"
    assert (await _sql("SELECT count(*) FROM llm_integration"))[0][0] == 0


async def test_nonprod_accepts_only_https(llm: Llm) -> None:
    llm.use(environment="staging")
    response = await llm.post("", {"name": "a", "endpoint": llm.server.endpoint})
    assert response.json()["detail"] == {
        "code": "llm_integration_invalid",
        "message": "Bu ortamda API adresi https:// ile başlamalı",
    }
    secure = await llm.post("", {"name": "b", "endpoint": "https://llm.corp.internal/v1"})
    assert secure.status_code == 201, secure.text
    assert (secure.json()["environment"], secure.json()["accepts_http"]) == ("nonprod", False)


async def test_the_key_is_stored_only_encrypted_and_never_returned(
    llm: Llm, llm_logs: RecordingHandler
) -> None:
    key = f"anahtar-{uuid4().hex}"
    response = await llm.post(
        "", {"name": "Anahtarlı", "endpoint": llm.server.endpoint, "api_key": key}
    )
    assert response.status_code == 201
    assert response.json()["item"]["has_key"] is True
    assert key not in response.text
    ((ciphertext,),) = await _sql(
        "SELECT api_key_ciphertext FROM llm_integration WHERE public_id = :p",
        p=response.json()["item"]["public_id"],
    )
    assert ciphertext.startswith("v1.") and key not in ciphertext
    dump = await _sql("SELECT row_to_json(l)::text FROM llm_integration l")
    assert all(key not in row[0] for row in dump)
    assert key not in (await llm.get()).text
    assert key not in llm_logs.rendered()
    # The key reaches only the server it was saved for.
    models = await llm.post("/models", {"public_id": response.json()["item"]["public_id"]})
    assert models.json()["ok"] is True
    assert llm.server.requests[-1].headers["authorization"] == f"Bearer {key}"


async def test_without_an_encryption_key_no_key_is_stored(llm: Llm) -> None:
    llm.use(settings_encryption_key=None)
    refused = await llm.post("", {"name": "a", "endpoint": llm.server.endpoint, "api_key": "k-123"})
    assert refused.json()["detail"] == {
        "code": "llm_key_storage_unavailable",
        "message": "Bu ortamda API anahtarı saklanamıyor; şifreleme anahtarı tanımlı değil.",
    }
    keyless = await llm.post("", {"name": "b", "endpoint": llm.server.endpoint})
    assert keyless.status_code == 201 and keyless.json()["key_storage"] is False


async def test_a_new_origin_without_a_new_key_deletes_the_key(
    llm: Llm, llm_logs: RecordingHandler
) -> None:
    item = await llm.create(api_key="k-1", chat_model="gemma-4-31b")
    target = f"/{item['public_id']}"
    same_origin = await llm.put(target, {"endpoint": llm.server.fake.url("/openai/v1")})
    assert same_origin.json()["key_cleared"] is False
    assert same_origin.json()["item"]["has_key"] is True
    moved = await llm.put(target, {"endpoint": f"http://localhost:{llm.server.fake.port}/v1"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["key_cleared"] is True and moved.json()["item"]["has_key"] is False
    ((ciphertext,),) = await _sql(
        "SELECT api_key_ciphertext FROM llm_integration WHERE public_id = :p", p=item["public_id"]
    )
    assert ciphertext is None
    actions = [e["action"] for e in llm_logs.events("llm_integration.changed")]
    assert "key_cleared" in actions
    rekeyed = await llm.put(target, {"endpoint": llm.server.endpoint, "api_key": "k-2"})
    assert rekeyed.json()["key_cleared"] is False and rekeyed.json()["item"]["has_key"] is True
    removed = await llm.put(target, {"api_key": ""})
    assert removed.json()["item"]["has_key"] is False and removed.json()["key_cleared"] is False


async def test_a_repeated_put_changes_nothing(llm: Llm, llm_logs: RecordingHandler) -> None:
    item = await llm.create(api_key="k-1", chat_model="gemma-4-31b")
    body = {"name": "Aynı", "chat_model": "qwen", "temperature": 0.5, "api_key": "k-1"}
    first = await llm.put(f"/{item['public_id']}", body)
    events = len(llm_logs.events("llm_integration.changed"))
    ((ciphertext, updated),) = await _sql(
        "SELECT api_key_ciphertext, updated_at FROM llm_integration WHERE public_id = :p",
        p=item["public_id"],
    )
    second = await llm.put(f"/{item['public_id']}", body)
    assert second.status_code == 200 and second.json()["item"] == first.json()["item"]
    assert len(llm_logs.events("llm_integration.changed")) == events
    assert await _sql(
        "SELECT api_key_ciphertext, updated_at FROM llm_integration WHERE public_id = :p",
        p=item["public_id"],
    ) == [(ciphertext, updated)]


async def test_a_changed_address_or_model_forgets_the_test_result(llm: Llm) -> None:
    item = await llm.create(chat_model="gemma-4-31b")
    target = f"/{item['public_id']}"
    assert (await llm.post("/test", {"public_id": item["public_id"], "record": True})).json()["ok"]
    assert (await llm.get()).json()["items"][0]["last_test"]["ok"] is True
    unchanged = await llm.put(target, {"temperature": 1})
    assert unchanged.json()["item"]["last_test"] is not None
    changed = await llm.put(target, {"chat_model": "qwen"})
    assert changed.json()["item"]["last_test"] is None


async def test_the_generation_model_and_its_reasoning_are_kept_beside_the_chat_model(
    llm: Llm,
) -> None:
    item = await llm.create(chat_model="gemma-4-31b")
    assert (
        item["generation_model"],
        item["generation_reasoning_effort"],
        item["judge_reasoning_effort"],
    ) == (
        "",
        "inherit",
        "inherit",
    )
    target = f"/{item['public_id']}"
    body = {
        "generation_model": " qwen/qwen3.8-27b ",
        "generation_reasoning_effort": "none",
        "judge_reasoning_effort": "low",
    }
    saved = (await llm.put(target, body)).json()["item"]
    assert (saved["chat_model"], saved["generation_model"]) == ("gemma-4-31b", "qwen/qwen3.8-27b")
    assert (saved["generation_reasoning_effort"], saved["judge_reasoning_effort"]) == (
        "none",
        "low",
    )
    # An absent field keeps its value; an unknown reasoning is refused.
    kept = (await llm.put(target, {"temperature": 1})).json()["item"]
    assert (
        kept["generation_model"] == "qwen/qwen3.8-27b" and kept["judge_reasoning_effort"] == "low"
    )
    refused = await llm.put(target, {"judge_reasoning_effort": "maximum"})
    assert refused.status_code == 422
    cleared = (
        await llm.put(target, {"generation_model": "", "generation_reasoning_effort": "inherit"})
    ).json()["item"]
    assert cleared["generation_model"] == "" and cleared["generation_reasoning_effort"] == "inherit"


# --- Requirement 4: the single active chat model ------------------------------------------------


async def test_a_chat_model_is_required_to_be_active(llm: Llm) -> None:
    created = await llm.post("", {"name": "a", "endpoint": llm.server.endpoint, "activate": True})
    assert created.json()["detail"] == {
        "code": "llm_chat_model_required",
        "message": "Önce bu entegrasyon için bir sohbet modeli seçin",
    }
    item = await llm.create()
    assert _error(await llm.put(f"/{item['public_id']}/active", {"active": True})) == (
        422,
        "llm_chat_model_required",
    )
    active = await llm.create(chat_model="gemma-4-31b", activate=True)
    emptied = await llm.put(f"/{active['public_id']}", {"chat_model": ""})
    assert _error(emptied) == (422, "llm_chat_model_required")


async def test_activation_takes_the_role_only_with_replace(llm: Llm) -> None:
    first = await llm.create(name="Birinci", chat_model="gemma-4-31b", activate=True)
    second = await llm.create(name="İkinci", chat_model="qwen")
    taken = await llm.put(f"/{second['public_id']}/active", {"active": True})
    assert _error(taken) == (409, "llm_chat_role_taken")
    assert taken.json()["detail"]["message"] == (
        "“Birinci” (Sohbet modeli) şu an bu rolde aktif. Pasif yapılıp yerine bu entegrasyon "
        "kullanılsın mı?"
    )
    assert (await llm.get()).json()["active"]["public_id"] == first["public_id"]
    replaced = await llm.put(f"/{second['public_id']}/active", {"active": True, "replace": True})
    assert replaced.status_code == 200
    body = replaced.json()
    assert body["active"] == {"public_id": second["public_id"], "name": "İkinci", "model": "qwen"}
    assert [entry["active"] for entry in body["items"]] == [False, True]
    created = await llm.post(
        "",
        {"name": "Üçüncü", "endpoint": llm.server.endpoint, "chat_model": "m", "activate": True},
    )
    assert _error(created) == (409, "llm_chat_role_taken")
    assert (await _sql("SELECT count(*) FROM llm_integration WHERE name = 'Üçüncü'"))[0][0] == 0
    off = await llm.put(f"/{second['public_id']}/active", {"active": False})
    assert off.json()["active"] is None


async def test_two_parallel_activations_let_one_win(llm: Llm) -> None:
    first = await llm.create(chat_model="gemma-4-31b")
    second = await llm.create(chat_model="qwen")
    responses = await asyncio.gather(
        llm.put(f"/{first['public_id']}/active", {"active": True}),
        llm.put(f"/{second['public_id']}/active", {"active": True}),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    rows = await _sql("SELECT count(*) FROM llm_integration WHERE active")
    assert rows[0][0] == 1


# --- Requirement 3: soft deletion ---------------------------------------------------------------


async def test_deletion_is_soft_and_empties_the_key(llm: Llm) -> None:
    item = await llm.create(api_key="k-1", chat_model="gemma-4-31b", activate=True)
    target = f"/{item['public_id']}"
    deleted = await llm.delete(target)
    assert deleted.status_code == 200
    assert deleted.json()["items"] == [] and deleted.json()["model_state"]["state"] == "none"
    ((is_deleted, active, ciphertext, deleted_by),) = await _sql(
        "SELECT is_deleted, active, api_key_ciphertext, deleted_by IS NOT NULL "
        "FROM llm_integration WHERE public_id = :p",
        p=item["public_id"],
    )
    assert (is_deleted, active, ciphertext, deleted_by) == (True, False, None, True)
    for response in (
        await llm.put(target, {"name": "x"}),
        await llm.put(f"{target}/active", {"active": True}),
        await llm.delete(target),
        await llm.post("/models", {"public_id": item["public_id"]}),
        await llm.post("/test", {"public_id": item["public_id"]}),
        await llm.delete(f"/{uuid4()}"),
    ):
        assert _error(response) == (404, "llm_integration_not_found")


# --- Requirement 12: the model state ------------------------------------------------------------


async def test_the_model_state_follows_the_active_server(llm: Llm) -> None:
    await llm.create(name="Etkin", chat_model="gemma-4-31b", activate=True)
    state = (await llm.get()).json()["model_state"]
    assert state == {
        "state": "ok",
        "model": "gemma-4-31b",
        "code": None,
        "reason": "",
        "name": "Etkin",
    }
    await llm.server.fake.close()
    other = await llm.create(name="Kapalı", chat_model="m", endpoint="http://127.0.0.1:9/v1")
    await llm.put(f"/{other['public_id']}/active", {"active": True, "replace": True})
    down = (await llm.get()).json()["model_state"]
    assert down["state"] == "down" and down["code"] == "connect_refused"
    assert down["reason"] == (
        "Model sunucusuna ulaşılamadı: bağlantı reddedildi — adres/port yanlış ya da sunucu kapalı"
    )


async def test_an_unreadable_key_is_reported_once_and_never_sent(
    llm: Llm, llm_logs: RecordingHandler
) -> None:
    item = await llm.create(api_key="k-1", chat_model="gemma-4-31b", activate=True)
    llm.use(settings_encryption_key=SecretStr(new_key()))
    sent = len(llm.server.requests)
    for _ in range(2):
        state = (await llm.get()).json()["model_state"]
        assert (state["state"], state["code"]) == ("down", "key_unreadable")
        assert state["reason"] == "Kayıtlı API anahtarı okunamadı; anahtarı yeniden girin"
    events = llm_logs.events("llm_integration.key_unreadable")
    assert events == [
        {"event": "llm_integration.key_unreadable", "integration_public_id": item["public_id"]}
    ]
    test = await llm.post("/test", {"public_id": item["public_id"]})
    assert test.json()["steps"] == [
        {
            "name": "Sunucu",
            "ok": False,
            "code": "key_unreadable",
            "detail": "Kayıtlı API anahtarı okunamadı; anahtarı yeniden girin",
            "ms": 0,
        }
    ]
    assert len(llm.server.requests) == sent


async def test_a_key_moved_to_another_origin_in_the_database_does_not_open(llm: Llm) -> None:
    item = await llm.create(api_key="k-1", chat_model="gemma-4-31b", activate=True)
    await _sql(
        "UPDATE llm_integration SET endpoint = :e WHERE public_id = :p",
        e=f"http://localhost:{llm.server.fake.port}/v1",
        p=item["public_id"],
    )
    assert (await llm.get()).json()["model_state"]["code"] == "key_unreadable"


# --- Requirement 14-16: model lists, inventory and the test -------------------------------------


async def test_the_model_list_of_a_form_and_of_a_saved_integration(llm: Llm) -> None:
    item = await llm.create(api_key="k-1", chat_model="qwen", activate=True)
    saved = await llm.post("/models", {"public_id": item["public_id"]})
    body = saved.json()
    assert body["ok"] and body["code"] is None and body["message"] == ""
    assert [(m["id"], m["in_use"]) for m in body["models"]] == [
        ("gemma-4-31b", False),
        ("qwen", True),
    ]
    # Another origin in the form: the saved key stays home.
    moved = await llm.post(
        "/models",
        {"public_id": item["public_id"], "endpoint": f"http://localhost:{llm.server.fake.port}/v1"},
    )
    assert moved.json()["ok"] and "authorization" not in llm.server.requests[-1].headers
    form_key = await llm.post(
        "/models",
        {
            "public_id": item["public_id"],
            "endpoint": f"http://localhost:{llm.server.fake.port}/v1",
            "api_key": "form-key",
        },
    )
    assert form_key.json()["ok"]
    assert llm.server.requests[-1].headers["authorization"] == "Bearer form-key"
    missing = await llm.post("/models", {"endpoint": " "})
    assert missing.json()["detail"] == {
        "code": "llm_integration_invalid",
        "message": "API adresi girilmedi",
    }
    down = await llm.post("/models", {"endpoint": "http://127.0.0.1:9/v1"})
    assert down.status_code == 200
    assert (down.json()["ok"], down.json()["code"]) == (False, "connect_refused")
    public = await llm.post("/models", {"endpoint": f"http://{PUBLIC_NAME}/v1"})
    assert public.json()["code"] == "network_policy_denied"
    assert public.json()["message"] == (
        "Model sunucusuna ulaşılamadı: adres kurum ağı dışında; istek gönderilmedi"
    )


async def test_the_inventory_lists_every_server(llm: Llm) -> None:
    first = await llm.create(name="Açık", chat_model="qwen", activate=True)
    await llm.create(name="Kapalı", endpoint="http://127.0.0.1:9/v1")
    broken = await llm.create(name="Bozuk", api_key="k-1")
    await _sql(
        "UPDATE llm_integration SET api_key_ciphertext = 'v1.AAAA.BBBB' WHERE public_id = :p",
        p=broken["public_id"],
    )
    servers = (await llm.get("/inventory")).json()["servers"]
    assert [(s["name"], s["ok"], s["code"]) for s in servers] == [
        ("Açık", True, None),
        ("Kapalı", False, "connect_refused"),
        ("Bozuk", False, "key_unreadable"),
    ]
    assert servers[0]["public_id"] == first["public_id"] and servers[0]["active"] is True
    assert [(m["id"], m["in_use"]) for m in servers[0]["models"]] == [
        ("gemma-4-31b", False),
        ("qwen", True),
    ]


async def test_the_connection_test_runs_both_steps_without_saving(llm: Llm) -> None:
    item = await llm.create(chat_model="gemma-4-31b")
    form = {"public_id": item["public_id"], "name": "yok sayılır", "chat_model": "qwen"}
    result = (await llm.post("/test", form)).json()
    assert result["ok"] is True
    assert [(s["name"], s["ok"], s["code"], s["detail"]) for s in result["steps"]] == [
        ("Sunucu", True, None, "Bağlantı kuruldu; sunucuda 2 model var"),
        ("Sohbet modeli", True, None, "Cevap verdi: “Ankara”"),
    ]
    chat = llm.server.requests[-1].json()
    assert chat["model"] == "qwen" and chat["max_tokens"] == 60
    assert chat["messages"][1]["content"] == "Türkiye'nin başkenti neresidir?"
    listing = (await llm.get()).json()
    assert listing["items"][0]["chat_model"] == "gemma-4-31b" and listing["active"] is None
    assert listing["items"][0]["last_test"] is None


async def test_a_failing_chat_step_names_a_model_the_server_does_not_offer(llm: Llm) -> None:
    llm.server.reply = "düz metin"
    result = (
        await llm.post("/test", {"endpoint": llm.server.endpoint, "chat_model": "baska-model"})
    ).json()
    assert result["ok"] is False
    assert result["steps"][1]["code"] == "invalid_json"
    assert result["steps"][1]["detail"] == (
        "model geçerli JSON üretmedi (model sunucunun listesinde yok)"
    )


async def test_a_recorded_test_is_not_a_connection_change(llm: Llm) -> None:
    item = await llm.create(chat_model="gemma-4-31b")
    ((before,),) = await _sql(
        "SELECT updated_at FROM llm_integration WHERE public_id = :p", p=item["public_id"]
    )
    recorded = await llm.post("/test", {"public_id": item["public_id"], "record": True})
    assert recorded.json()["ok"] is True
    ((after, ok, summary),) = await _sql(
        "SELECT updated_at, last_test_ok, last_test_summary FROM llm_integration "
        "WHERE public_id = :p",
        p=item["public_id"],
    )
    assert (after, ok, summary) == (before, True, "Sunucu: ✓; Sohbet modeli: ✓")
    with_fields = await llm.post(
        "/test", {"public_id": item["public_id"], "record": True, "chat_model": "qwen"}
    )
    assert _error(with_fields) == (422, "invalid_request")
    without_id = await llm.post("/test", {"endpoint": llm.server.endpoint, "record": True})
    assert _error(without_id) == (422, "invalid_request")


# --- Requirement 5: the next analysis uses the new connection -----------------------------------


async def test_the_next_analysis_uses_a_newly_activated_connection(llm: Llm) -> None:
    other_fake = await FakeLlmServer().start()
    other = ModelServer(other_fake, ("yeni-model",))
    other.reply = '{"cevap": "ikinci"}'
    try:
        await llm.create(name="Eski", chat_model="gemma-4-31b", activate=True, api_key="k-1")
        settings = llm.auth.settings
        gateway = LlmGateway(
            port=llm.adapter,
            session_factory=async_session_factory,
            keys=lambda: ConnectionKeys(settings),
        )
        ((tenant_id,),) = await _sql(
            "SELECT tenant_id FROM tenant WHERE public_id = :p", p=llm.manager.tenant_id
        )
        tenant = {"tenant_id": int(tenant_id), "tenant_public_id": llm.manager.tenant_id}
        first = await gateway.snapshot(**tenant)
        assert isinstance(first, LlmConnection) and first.api_key == "k-1"
        newer = await llm.create(name="Yeni", endpoint=other.endpoint, chat_model="yeni-model")
        await llm.put(f"/{newer['public_id']}/active", {"active": True, "replace": True})
        snapshot = await gateway.snapshot(**tenant)
        assert isinstance(snapshot, LlmConnection)
        assert (snapshot.endpoint, snapshot.chat_model, snapshot.api_key) == (
            other.endpoint,
            "yeni-model",
            None,
        )
        result = await gateway.port.chat(
            snapshot,
            LlmChatRequest(
                system="s", user="u", schema={}, max_tokens=10, purpose=LlmPurpose.ANALYSIS
            ),
        )
        assert result.value == {"cevap": "ikinci"}
        assert [request.method for request in other.requests].count("POST") == 1
        assert result.summary.integration_public_id == newer["public_id"]
        state = await gateway.model_state(**tenant)
        assert (state.state, state.model) == ("ok", "yeni-model")
        await llm.delete(f"/{newer['public_id']}")
        assert await gateway.snapshot(**tenant) is LlmOutcome.NOT_CONFIGURED
    finally:
        await other_fake.close()


# --- Requirement 22: no content in responses or logs ----------------------------------------------


async def test_server_texts_never_reach_responses_or_logs(
    llm: Llm, llm_logs: RecordingHandler
) -> None:
    marker = f"ISARET-{uuid4().hex}"

    async def failing(request: RecordedRequest, reader: Any, writer: Writer) -> None:
        if request.method == "GET":
            writer.write(models_reply("gemma-4-31b"))
        else:
            writer.write(json_response({"error": {"message": f"iç hata {marker}"}}, 500))
        await writer.drain()

    llm.server.fake.scenario = failing
    key = f"anahtar-{marker}"
    item = await llm.create(name=f"Ad {marker}", chat_model="gemma-4-31b", api_key=key)
    result = await llm.post("/test", {"public_id": item["public_id"]})
    step = result.json()["steps"][1]
    assert (step["code"], step["detail"]) == ("upstream_status", "Sunucu HTTP 500 döndürdü")
    bad = await llm.post("", {"name": "x", "endpoint": f"http://{marker}.example/v1?{marker}"})
    assert bad.status_code == 422 and marker not in bad.text
    rendered = llm_logs.rendered()
    assert marker not in rendered and key not in rendered
    assert "llm.call" in rendered and "llm.probe" in rendered
