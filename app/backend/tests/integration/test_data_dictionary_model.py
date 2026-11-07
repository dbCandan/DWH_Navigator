"""The migrated dictionary, word list and settings tables (Veri ve geçiş of 001, 002, 009).

The mandatory block and comments (rules/41 and 43), the PRDs' documented deviations from the block
(record rows of a version, item rows of a list, the settings mapping), the database rules behind
the requirements (one active version, any number of kept ones, unique current terms and positions) and the
three migrations going down and up again.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings
from app.db.session import async_session_factory, engine

pytestmark = pytest.mark.integration

BLOCK = {
    "props": "jsonb",
    "created_at": "timestamp with time zone",
    "updated_at": "timestamp with time zone",
    "created_by": "bigint",
    "updated_by": "bigint",
    "is_deleted": "boolean",
    "deleted_at": "timestamp with time zone",
    "deleted_by": "bigint",
}
NOT_IN_RECORDS = {"public_id", "updated_at", "updated_by", "is_deleted", "deleted_at", "deleted_by"}
TABLES = {
    # table: (has public_id, full block, commented columns)
    "dictionary_version": (True, True, ("status", "version", "content_digest", "warnings")),
    "dictionary_object_record": (False, False, ("position", "object_key", "props")),
    "dictionary_column_record": (False, False, ("position", "column_name", "synonyms")),
    "vocabulary_list": (True, True, ("public_id", "revision", "content_digest", "last_source")),
    "vocabulary_term": (False, True, ("position", "term_key", "equivalents")),
    "vocabulary_stopword": (False, True, ("position", "word_key", "group_name")),
    "search_setting": (False, True, ("setting_key", "value")),
}


async def _scalar(connection: AsyncConnection, sql: str, **params: Any) -> Any:
    return (await connection.execute(text(sql), params)).scalar_one()


async def _columns(connection: AsyncConnection, table: str) -> dict[str, str]:
    rows = await connection.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = :table"
        ),
        {"table": table},
    )
    return {str(name): str(kind) for name, kind in rows.all()}


async def test_the_tables_carry_the_block_its_deviations_and_comments(
    migrated_database: None,
) -> None:
    async with engine.connect() as connection:
        for table, (public_id, full_block, commented) in TABLES.items():
            comment = await _scalar(
                connection, "SELECT obj_description(CAST(:t AS regclass), 'pg_class')", t=table
            )
            assert comment, table
            columns = await _columns(connection, table)
            assert "timestamp without time zone" not in columns.values(), table
            assert ("public_id" in columns) is public_id, table
            if full_block:
                for column, kind in BLOCK.items():
                    assert columns[column] == kind, (table, column)
            else:
                assert NOT_IN_RECORDS.isdisjoint(columns), table
                assert columns["props"] == "jsonb" and "created_at" in columns
            for column in commented:
                described = await _scalar(
                    connection,
                    "SELECT col_description(CAST(:t AS regclass), attnum) FROM pg_attribute "
                    "WHERE attrelid = CAST(:t AS regclass) AND attname = :c",
                    t=table,
                    c=column,
                )
                assert described, (table, column)
        indexes = dict(
            (
                await connection.execute(
                    text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")
                )
            ).all()
        )
    for name in (
        "uq_dictionary_version_tenant_active",
        "uq_vocabulary_term_tenant_term_key",
        "uq_vocabulary_term_tenant_position",
        "uq_vocabulary_stopword_tenant_position",
        "uq_search_setting_tenant_key",
    ):
        assert "UNIQUE" in indexes[name] and "is_deleted = false" in indexes[name], name
    assert "is_deleted = false" in indexes["ix_dictionary_version_active_public_id"]
    assert "word_key" not in "".join(
        d for n, d in indexes.items() if n.startswith("uq_vocabulary_stopword")
    )


async def _tenant() -> int:
    async with engine.connect() as connection:
        return int(
            await _scalar(connection, "SELECT tenant_id FROM tenant WHERE code = 'platform'")
        )


_VERSION = (
    "INSERT INTO dictionary_version (public_id, tenant_id, status, version, content_digest, "
    "source_name, channel, imported_at, row_count, column_count, object_count, warning_count, "
    "is_deleted) VALUES (gen_random_uuid()::text, :tenant, :status, 'v-1', :digest, :name, "
    ":channel, now(), 1, 1, 1, 0, :deleted)"
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "eski"},
        {"channel": "api"},
        {"digest": "XYZ"},
        {"name": ""},
        {"status": "pruned", "deleted": False},
        {"status": "active", "deleted": True},
    ],
)
async def test_the_database_refuses_invalid_versions(
    migrated_database: None, overrides: dict[str, Any]
) -> None:
    values = {
        "tenant": await _tenant(),
        "status": "previous",
        "digest": "0123456789ab",
        "name": "s.xlsx",
        "channel": "arayuz",
        "deleted": False,
    } | overrides
    async with async_session_factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(text(_VERSION), values)
        await session.rollback()


async def test_one_active_version_per_tenant_and_many_kept(migrated_database: None) -> None:
    tenant = await _tenant()
    base = {"tenant": tenant, "digest": "0123456789ab", "name": "s.xlsx", "channel": "betik"}
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM dictionary_column_record"))
        await session.execute(text("DELETE FROM dictionary_object_record"))
        await session.execute(text("DELETE FROM dictionary_version"))
        await session.execute(text(_VERSION), base | {"status": "active", "deleted": False})
        for _ in range(2):
            await session.execute(text(_VERSION), base | {"status": "previous", "deleted": False})
            await session.execute(text(_VERSION), base | {"status": "pruned", "deleted": True})
        await session.commit()
        with pytest.raises(DBAPIError):
            await session.execute(text(_VERSION), base | {"status": "active", "deleted": False})
        await session.rollback()
        await session.execute(text("DELETE FROM dictionary_version"))
        await session.commit()


def test_the_migrations_go_down_and_up(migrated_database: None) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    tables = set(TABLES)

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
        command.downgrade(config, "202610080002")
        assert tables.isdisjoint(asyncio.run(present()))
    finally:
        command.upgrade(config, "head")
    assert tables <= asyncio.run(present())
    command.check(config)
