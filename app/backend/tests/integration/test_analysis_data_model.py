"""The migrated analysis record and saved answer tables (Veri ve geçiş of data-dictionary
004-question-analysis and 008-analysis-records).

analysis_record carries the mandatory block and refuses a soft deletion (Decision 13); saved_answer
has no soft-delete columns (Decision 9); comments are written (rules/43); deleting a record empties
the saved answer's link; the migration goes down and up again.
"""

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from tests.integration.conftest import AuthHarness
from tests.integration.test_data_dictionary_model import BLOCK, _columns, _scalar

pytestmark = pytest.mark.integration

SOFT_DELETE = {"is_deleted", "deleted_at", "deleted_by"}


async def test_the_block_its_deviations_and_comments(migrated_database: None) -> None:
    async with engine.connect() as connection:
        record = await _columns(connection, "analysis_record")
        for column, kind in BLOCK.items():
            assert record[column] == kind, column
        saved = await _columns(connection, "saved_answer")
        assert SOFT_DELETE.isdisjoint(saved)
        assert {"props", "created_at", "updated_at", "created_by", "updated_by"} <= set(saved)
        assert "ip" not in record and "host" not in record
        for table, columns in (
            ("analysis_record", ("state", "flow", "result", "steps", "search_key", "asked_by")),
            ("saved_answer", ("text_key", "meaning_key", "fingerprint", "result")),
        ):
            assert await _scalar(
                connection, "SELECT obj_description(CAST(:t AS regclass), 'pg_class')", t=table
            )
            for column in columns:
                assert await _scalar(
                    connection,
                    "SELECT col_description(CAST(:t AS regclass), attnum) FROM pg_attribute "
                    "WHERE attrelid = CAST(:t AS regclass) AND attname = :c",
                    t=table,
                    c=column,
                ), (table, column)


async def _tenant_and_user() -> tuple[int, int | None]:
    async with engine.connect() as connection:
        tenant = int(
            await _scalar(connection, "SELECT tenant_id FROM tenant WHERE code = 'platform'")
        )
        user = await _scalar(connection, "SELECT min(user_id) FROM app_user")
    return tenant, None if user is None else int(user)


_RECORD = (
    "INSERT INTO analysis_record (public_id, tenant_id, asked_by, state, flow, asked_at, query, "
    "fresh, origin, is_deleted) VALUES (:p, :t, :u, :state, :flow, now(), :q, false, :origin, "
    ":deleted)"
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"deleted": True},
        {"state": "bitti"},
        {"flow": "önbellek"},
        {"state": "running", "flow": "analyst"},
        {"state": "completed", "flow": None},
        {"origin": "dosya"},
        {"q": ""},
    ],
)
async def test_the_database_refuses_invalid_records(
    auth: AuthHarness, overrides: dict[str, object]
) -> None:
    await auth.super_admin()
    tenant, user = await _tenant_and_user()
    values = {"p": "x-1", "t": tenant, "u": user, "state": "completed", "flow": "analyst",
              "q": "kart", "origin": "question", "deleted": False} | overrides  # fmt: skip
    async with async_session_factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(text(_RECORD), values)
        await session.rollback()


def test_the_migration_goes_down_and_up(migrated_database: None) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    tables = {"analysis_record", "saved_answer"}

    async def present() -> set[str]:
        probe = create_async_engine(get_settings().database_url)
        try:
            async with probe.connect() as connection:
                rows = await connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
                return {str(row[0]) for row in rows}
        finally:
            await probe.dispose()

    asyncio.run(engine.dispose())
    try:
        command.downgrade(config, "202610080005")
        assert tables.isdisjoint(asyncio.run(present()))
    finally:
        command.upgrade(config, "head")
    assert tables <= asyncio.run(present())
    command.check(config)
