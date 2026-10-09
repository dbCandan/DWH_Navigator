"""Shared PostgreSQL integration fixtures: one Alembic upgrade per run, real HTTP application."""

import logging
import secrets
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient, Response

from app.api.auth.endpoints import REFRESH_COOKIE_NAME, get_login_rate_limiter
from app.core.config import Settings, get_settings
from app.core.logging import JsonFormatter
from app.core.login_throttle import LoginRateLimiter
from app.db.session import async_session_factory, engine
from app.main import app
from app.services.super_admin_service import ensure_super_admin

if TYPE_CHECKING:
    from tests.integration.data_dictionary import DataDictionary

CLIENT_ADDRESS = "10.0.0.5"


@pytest.fixture(scope="session")
def migrated_database(postgres_database_url: str) -> Iterator[None]:
    del postgres_database_url  # the Alembic environment reads the same typed setting
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    yield


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test() -> AsyncIterator[None]:
    # Each test runs in its own event loop; pooled asyncpg connections must not outlive it.
    yield
    await engine.dispose()


def new_password() -> str:
    """A test-process password that meets the policy; never a usable password elsewhere."""

    return f"deneme {secrets.token_hex(12)} parola"


def new_name(prefix: str = "kisi") -> str:
    return f"{prefix}.{uuid4().hex[:10]}"


@dataclass(frozen=True)
class SignedIn:
    """A session obtained through the real login or password-change endpoint."""

    username: str
    password: str
    public_id: str
    body: dict[str, Any]
    refresh_token: str

    @property
    def access_token(self) -> str:
        return str(self.body["access_token"])

    @property
    def tenant_id(self) -> str:
        return str(self.body["user"]["tenant_id"])


@dataclass(frozen=True)
class OpenedAccount:
    username: str
    public_id: str
    one_time_password: str
    body: dict[str, Any]


class AuthHarness:
    """The real application on a test client, with settings and limiter under test control."""

    def __init__(
        self,
        client: AsyncClient,
        limiter: LoginRateLimiter,
        state: dict[str, Settings],
    ) -> None:
        self.client = client
        self.limiter = limiter
        self._state = state

    @property
    def settings(self) -> Settings:
        return self._state["settings"]

    def use_settings(self, **updates: Any) -> Settings:
        self._state["settings"] = self._state["settings"].model_copy(update=updates)
        return self._state["settings"]

    @property
    def prefix(self) -> str:
        return self.settings.api_prefix

    def origin(self) -> dict[str, str]:
        return {"origin": self.settings.public_origin}

    def headers(self, session: SignedIn) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {session.access_token}",
            self.settings.tenant_header: session.tenant_id,
        }

    async def login(self, username: str, password: str, **kwargs: Any) -> Response:
        self.client.cookies.clear()
        return await self.client.post(
            f"{self.prefix}/auth/login",
            json={"username": username, "password": password},
            **kwargs,
        )

    async def change_password(
        self, username: str, current: str, new: str, **kwargs: Any
    ) -> Response:
        self.client.cookies.clear()
        return await self.client.post(
            f"{self.prefix}/auth/password",
            json={"username": username, "current_password": current, "new_password": new},
            **kwargs,
        )

    def cookie_header(self, token: str | None) -> dict[str, str]:
        return {"cookie": f"{REFRESH_COOKIE_NAME}={token}"} if token is not None else {}

    async def refresh(self, token: str | None, headers: dict[str, str] | None = None) -> Response:
        self.client.cookies.clear()
        return await self.client.post(
            f"{self.prefix}/auth/refresh",
            headers={**self.origin(), **self.cookie_header(token), **(headers or {})},
        )

    async def logout(self, token: str | None) -> Response:
        self.client.cookies.clear()
        return await self.client.post(
            f"{self.prefix}/auth/logout", headers={**self.origin(), **self.cookie_header(token)}
        )

    @staticmethod
    def refresh_cookie(response: Response) -> str:
        token = response.cookies.get(REFRESH_COOKIE_NAME)
        assert token, response.headers.get("set-cookie")
        return str(token)

    def signed_in(self, username: str, password: str, response: Response) -> SignedIn:
        assert response.status_code == 200, response.text
        body = response.json()
        return SignedIn(
            username=username,
            password=password,
            public_id=str(body["user"]["public_id"]),
            body=body,
            refresh_token=self.refresh_cookie(response),
        )

    async def sign_in(self, username: str, password: str) -> SignedIn:
        return self.signed_in(username, password, await self.login(username, password))

    async def activate(self, username: str, one_time_password: str) -> SignedIn:
        """Set the account's own password with its one-time password, as at the first login."""

        password = new_password()
        response = await self.change_password(username, one_time_password, password)
        return self.signed_in(username, password, response)

    async def super_admin(self) -> SignedIn:
        """A fresh super admin from the operator path, with its own password already set."""

        username = new_name("yonetici")
        start_up = new_password()
        async with async_session_factory() as session:
            await ensure_super_admin(session, username=username, password=start_up)
        return await self.activate(username, start_up)

    async def open_account(self, admin: SignedIn, role: str = "kullanici") -> OpenedAccount:
        username = new_name()
        response = await self.client.post(
            f"{self.prefix}/admin/users",
            json={"username": username, "display_name": "Ayşe Işık", "role": role},
            headers=self.headers(admin),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        return OpenedAccount(
            username=username,
            public_id=str(body["user"]["public_id"]),
            one_time_password=str(body["one_time_password"]),
            body=body,
        )

    async def account(self, admin: SignedIn, role: str = "kullanici") -> SignedIn:
        opened = await self.open_account(admin, role)
        return await self.activate(opened.username, opened.one_time_password)


@pytest.fixture
async def auth(migrated_database: None) -> AsyncIterator[AuthHarness]:
    state = {"settings": get_settings().model_copy(update={"environment": "staging"})}
    limiter = LoginRateLimiter()
    app.dependency_overrides[get_settings] = lambda: state["settings"]
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    transport = ASGITransport(app=app, client=(CLIENT_ADDRESS, 50000))
    try:
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            yield AuthHarness(client, limiter, state)
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_login_rate_limiter, None)


@pytest.fixture
async def dd(auth: AuthHarness) -> AsyncIterator["DataDictionary"]:
    """A fresh installation's data dictionary, a started search index and a manager."""

    # Imported here: the harness module imports this one.
    from tests.integration.data_dictionary import data_dictionary_harness

    async for harness in data_dictionary_harness(auth):
        yield harness


class RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def events(self, name: str) -> list[dict[str, Any]]:
        return [
            dict(getattr(record, "structured_fields", {}))
            for record in self.records
            if record.getMessage() == name
        ]

    def records_of(self, logger: str) -> list[dict[str, Any]]:
        """The structured fields of every event one logger wrote, in order."""

        return [
            dict(getattr(record, "structured_fields", {}))
            for record in self.records
            if record.name == logger and hasattr(record, "structured_fields")
        ]

    def rendered(self) -> str:
        formatter = JsonFormatter()
        return "\n".join(formatter.format(record) for record in self.records)


@pytest.fixture
def recorded_logs() -> Iterator[RecordingHandler]:
    """Every record that reaches the root logger, application events at INFO included."""

    handler = RecordingHandler()
    loggers = [
        logging.getLogger(name)
        for name in (
            "app.auth",
            "app.admin",
            "app.http",
            "app.security",
            "app.dictionary",
            "app.vocabulary",
            "app.search",
            "app.feedback",
            "app.lists",
            "app.explorer",
        )
    ]
    levels = [logger.level for logger in loggers]
    root = logging.getLogger()
    root.addHandler(handler)
    for logger in loggers:
        logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        for logger, level in zip(loggers, levels, strict=True):
            logger.setLevel(level)
