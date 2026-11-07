"""Shared setup of the data-dictionary integration tests (dictionary, word lists, settings).

Every test starts from the state of a fresh installation: no dictionary, the seed word lists
loaded by the migration's own function, no changed setting, and a new search index on the
application, started against the real database.
"""

import importlib.util
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from httpx import Response
from sqlalchemy import Connection, text

from app.db.session import async_session_factory, engine
from app.infrastructure.excel.writer import XLSX_MEDIA_TYPE
from app.main import app
from app.services.search_index import SearchIndex, build_engine
from tests.dictionary_seed import DEFAULT_NAME, Seeded, seed_through_index
from tests.integration.conftest import AuthHarness, SignedIn, visitor_headers

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "app" / "backend"
SYNTHETIC_WORKBOOK = BACKEND / "tests" / "fixtures" / "parity" / "sozluk_sentetik.xlsx"
VOCABULARY_MIGRATION = ROOT / "schema" / "alembic" / "versions" / "202610080004_vocabulary_lists.py"


def vocabulary_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vocabulary_migration", VOCABULARY_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_seed(connection: Connection, directory: Path | None = None) -> None:
    """The migration's seed step on ``connection``, as the migration Job runs it."""

    module = vocabulary_migration()
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        if directory is None:
            module.load_seed_lists()
        else:
            module.load_seed_lists(directory)


async def sql(statement: str, **params: Any) -> list[Any]:
    async with async_session_factory() as session:
        result = await session.execute(text(statement), params)
        rows = list(result.all()) if result.returns_rows else []
        await session.commit()
    return rows


async def reset_data_dictionary() -> None:
    async with engine.begin() as connection:
        for table in (
            "dictionary_sync_run",
            "dictionary_source",
            "dictionary_column_record",
            "dictionary_object_record",
            "dictionary_version",
            "search_setting",
            "vocabulary_term",
            "vocabulary_stopword",
            "vocabulary_list",
        ):
            await connection.execute(text(f"DELETE FROM {table}"))
        await connection.run_sync(run_seed)


async def database_ready() -> bool:
    return True


def _no_exit() -> None:
    raise AssertionError("the search index stopped the process")


async def started_index(**options: Any) -> SearchIndex:
    index = SearchIndex(async_session_factory, **options)
    await index.run_startup(database_ready, _no_exit)
    return index


@dataclass
class DataDictionary:
    """The real application with a manager and the data-dictionary endpoints at hand."""

    auth: AuthHarness
    admin: SignedIn
    manager: SignedIn

    @property
    def index(self) -> SearchIndex:
        index: SearchIndex = app.state.search_index
        return index

    def use_index(self, index: SearchIndex) -> None:
        app.state.search_index = index

    def url(self, path: str) -> str:
        return f"{self.auth.prefix}{path}"

    def headers(self, who: SignedIn | None = None) -> dict[str, str]:
        person = who or self.manager
        # The session opens the administration; the device id makes the same person a visitor
        # on the main screen (application-foundation 003-anonymous-visitor Decision 3).
        return {**self.auth.headers(person), **visitor_headers(person), **self.auth.origin()}

    async def request(
        self, method: str, path: str, who: SignedIn | None = None, **kwargs: Any
    ) -> Response:
        headers = {**self.headers(who), **kwargs.pop("headers", {})}
        return await self.auth.client.request(method, self.url(path), headers=headers, **kwargs)

    async def get(self, path: str, who: SignedIn | None = None) -> Response:
        return await self.request("GET", path, who)

    async def upload(
        self,
        path: str,
        data: bytes,
        *,
        name: str = "sozluk.xlsx",
        media_type: str = XLSX_MEDIA_TYPE,
        who: SignedIn | None = None,
    ) -> Response:
        return await self.request(
            "POST",
            path,
            who,
            content=data,
            headers={"Content-Type": media_type, "X-Filename": name},
        )

    async def seed_dictionary(self, data: bytes, name: str = DEFAULT_NAME) -> Seeded:
        """A workbook written as the manager's version, through the search index."""

        ((user_id,),) = await sql(
            "SELECT user_id FROM app_user WHERE public_id = :p", p=self.manager.public_id
        )
        return await seed_through_index(self.index, data, name=name, user_id=int(user_id))

    async def put_list(self, kind: str, items: Any, who: SignedIn | None = None) -> Response:
        return await self.request("PUT", f"/vocabulary/{kind}", who, json={"items": items})

    async def patch_settings(self, values: Any, who: SignedIn | None = None) -> Response:
        return await self.request("PATCH", "/search-settings", who, json={"values": values})


def first_then(later: Callable[..., Any]) -> Callable[..., Any]:
    """An engine builder that builds the first engine and then behaves like ``later``."""

    calls = {"n": 0}

    def builder(*args: Any) -> Any:
        calls["n"] += 1
        return build_engine(*args) if calls["n"] == 1 else later(*args)

    return builder


def error(response: Response) -> tuple[int, str]:
    return response.status_code, str(response.json()["detail"]["code"])


async def data_dictionary_harness(
    auth: AuthHarness, index_options: dict[str, Any] | None = None
) -> AsyncIterator[DataDictionary]:
    await reset_data_dictionary()
    previous = app.state.search_index
    app.state.search_index = await started_index(**(index_options or {}))
    try:
        admin = await auth.super_admin()
        manager = await auth.account(admin, "yonetici")
        yield DataDictionary(auth, admin, manager)
    finally:
        app.state.search_index = previous
