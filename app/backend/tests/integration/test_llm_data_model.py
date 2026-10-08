"""The migrated llm_integration table (data-dictionary 003-llm-connection Veri ve geçiş).

The mandatory block and comments (rules/41 and 43), the database rules behind Requirement 2-4
(single active row under concurrency, an active row has a model, ranges and the closed set of
reasoning efforts), and the migration going down and up again.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings
from app.db.session import async_session_factory, engine

pytestmark = pytest.mark.integration

MANDATORY_COLUMNS = {
    "public_id": "text",
    "props": "jsonb",
    "created_at": "timestamp with time zone",
    "updated_at": "timestamp with time zone",
    "created_by": "bigint",
    "updated_by": "bigint",
    "is_deleted": "boolean",
    "deleted_at": "timestamp with time zone",
    "deleted_by": "bigint",
}
COMMENTED_COLUMNS = (
    "tenant_id",
    "name",
    "name_key",
    "endpoint",
    "api_key_ciphertext",
    "active",
    "chat_model",
    "temperature",
    "timeout_seconds",
    "reasoning_effort",
    "seed",
    "last_test_at",
    "last_test_ok",
    "last_test_summary",
)


async def _scalar(connection: AsyncConnection, sql: str, **params: Any) -> Any:
    return (await connection.execute(text(sql), params)).scalar_one()


async def _tenant_id() -> int:
    async with engine.connect() as connection:
        value = await _scalar(connection, "SELECT tenant_id FROM tenant WHERE code = 'platform'")
    return int(value)


_INSERT = (
    "INSERT INTO llm_integration (public_id, tenant_id, name, name_key, endpoint, chat_model, "
    "active, temperature, timeout_seconds, reasoning_effort, seed, is_deleted, "
    "api_key_ciphertext, last_test_at) VALUES (gen_random_uuid()::text, :tenant, :name, :key, "
    "'http://10.0.0.5/v1', :model, :active, :temperature, :timeout, :effort, :seed, :deleted, "
    ":cipher, :tested)"
)


def _row(tenant: int, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "tenant": tenant,
        "name": "Satır",
        "key": "satir",
        "model": "m",
        "active": False,
        "temperature": 0.0,
        "timeout": 900,
        "effort": "none",
        "seed": 42,
        "deleted": False,
        "cipher": None,
        "tested": None,
    }
    values.update(overrides)
    return values


async def test_the_table_carries_the_block_comments_and_partial_indexes(
    migrated_database: None,
) -> None:
    async with engine.connect() as connection:
        comment = await _scalar(
            connection, "SELECT obj_description('llm_integration'::regclass, 'pg_class')"
        )
        assert comment and "llm-connection" in comment
        columns = dict(
            (
                await connection.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = 'llm_integration'"
                    )
                )
            ).all()
        )
        for column, data_type in MANDATORY_COLUMNS.items():
            assert columns[column] == data_type, column
        assert columns["temperature"] == "double precision"
        assert "timestamp without time zone" not in columns.values()
        for column in COMMENTED_COLUMNS:
            described = await _scalar(
                connection,
                "SELECT col_description('llm_integration'::regclass, attnum) FROM pg_attribute "
                "WHERE attrelid = 'llm_integration'::regclass AND attname = :column",
                column=column,
            )
            assert described, column
        indexes = dict(
            (
                await connection.execute(
                    text(
                        "SELECT indexname, indexdef FROM pg_indexes "
                        "WHERE tablename = 'llm_integration'"
                    )
                )
            ).all()
        )
    assert "WHERE (is_deleted = false)" in indexes["ix_llm_integration_active_public_id"]
    assert "UNIQUE" in indexes["uq_llm_integration_tenant_name_key"]
    assert "WHERE (is_deleted = false)" in indexes["uq_llm_integration_tenant_name_key"]
    assert "UNIQUE" in indexes["uq_llm_integration_tenant_active"]
    assert "WHERE (active AND (is_deleted = false))" in indexes["uq_llm_integration_tenant_active"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "x" * 101, "key": "x"},
        {"active": True, "model": ""},
        {"active": True, "deleted": True},
        {"deleted": True, "cipher": "v1.a.b"},
        {"temperature": 2.5},
        {"temperature": -0.1},
        {"timeout": 4},
        {"timeout": 3601},
        {"effort": "max"},
        {"seed": -2},
        {"tested": datetime(2026, 10, 8, 10, tzinfo=UTC)},
    ],
)
async def test_the_database_refuses_invalid_rows(
    migrated_database: None, overrides: dict[str, Any]
) -> None:
    tenant = await _tenant_id()
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM llm_integration"))
        await session.commit()
        # A length over the column type stops at the type, every other rule at a constraint.
        with pytest.raises(DBAPIError):
            await session.execute(text(_INSERT), _row(tenant, **overrides))
        await session.rollback()


async def test_one_active_row_per_tenant_even_under_concurrency(migrated_database: None) -> None:
    tenant = await _tenant_id()
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM llm_integration"))
        await session.execute(text(_INSERT), _row(tenant, name="A", key="a"))
        await session.execute(text(_INSERT), _row(tenant, name="B", key="b"))
        await session.commit()

    first = async_session_factory()
    second = async_session_factory()
    try:
        await first.execute(text("UPDATE llm_integration SET active = true WHERE name = 'A'"))
        blocked = asyncio.create_task(
            second.execute(text("UPDATE llm_integration SET active = true WHERE name = 'B'"))
        )
        await asyncio.sleep(0.2)
        assert not blocked.done()  # the unique index makes the second wait for the first
        await first.commit()
        with pytest.raises(IntegrityError):
            await blocked
        await second.rollback()
    finally:
        await first.close()
        await second.close()

    async with async_session_factory() as session:
        names = (
            await session.execute(text("SELECT name FROM llm_integration WHERE active"))
        ).scalars()
        assert list(names) == ["A"]
        # A deleted row frees its name and never counts as active.
        await session.execute(
            text("UPDATE llm_integration SET active = false, is_deleted = true WHERE name = 'A'")
        )
        await session.execute(text(_INSERT), _row(tenant, name="A", key="a", active=True))
        await session.execute(text("DELETE FROM llm_integration"))
        await session.commit()


def test_the_migration_goes_down_and_up(migrated_database: None) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))

    async def tables() -> set[str]:
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
        command.downgrade(config, "202610080001")
        assert "llm_integration" not in asyncio.run(tables())
    finally:
        command.upgrade(config, "head")
    assert "llm_integration" in asyncio.run(tables())
    command.check(config)
