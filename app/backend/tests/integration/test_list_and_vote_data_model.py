"""The migrated term list and vote tables (Veri ve geçiş of data-dictionary 005-list-search and
006-answer-feedback).

term_list carries the mandatory block and refuses a soft deletion; term_list_item is a dependent
row without public_id, deleted with its list; answer_vote is an append-only stream without
public_id, update or soft-delete columns. Comments are written (rules/43), the database refuses a
second running list of a tenant and invalid values, and both migrations go down and up again.
"""

import asyncio
from datetime import UTC, datetime
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
from tests.integration.data_dictionary import sql
from tests.integration.test_data_dictionary_model import BLOCK, _columns, _scalar

pytestmark = pytest.mark.integration

STARTED = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)

SOFT_DELETE = {"is_deleted", "deleted_at", "deleted_by"}
COMMENTED = {
    "term_list": ("status", "stop_requested", "owner_id", "run_started_at", "elapsed_before_ms"),
    "term_list_item": ("position", "answer", "flow", "error_message"),
    "answer_vote": ("voter_id", "text_key", "meaning_key", "scope", "table_key", "note"),
}


async def test_the_blocks_their_deviations_and_comments(migrated_database: None) -> None:
    async with engine.connect() as connection:
        lists = await _columns(connection, "term_list")
        for column, kind in BLOCK.items():
            assert lists[column] == kind, column
        assert "public_id" in lists
        terms = await _columns(connection, "term_list_item")
        assert "public_id" not in terms and SOFT_DELETE.isdisjoint(terms)
        assert {"props", "created_at", "updated_at", "created_by", "updated_by"} <= set(terms)
        votes = await _columns(connection, "answer_vote")
        assert "public_id" not in votes
        assert {"updated_at", "updated_by", *SOFT_DELETE}.isdisjoint(votes)
        assert {"props", "created_at", "created_by"} <= set(votes)
        for table, columns in COMMENTED.items():
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


_LIST = (
    "INSERT INTO term_list (public_id, tenant_id, owner_id, file_name, header, status, "
    "term_count, dictionary_version, run_started_at, is_deleted) VALUES (gen_random_uuid()::text, "
    ":t, :u, 'a.xlsx', 'Terim', :status, :count, 'v', :started, :deleted) RETURNING term_list_id"
)


async def _ids() -> tuple[int, int]:
    rows = await sql("SELECT home_tenant_id, user_id FROM app_user ORDER BY user_id LIMIT 1")
    return int(rows[0][0]), int(rows[0][1])


async def test_the_database_keeps_the_list_rules(auth: AuthHarness) -> None:
    await auth.super_admin()
    await sql("DELETE FROM term_list")
    tenant, user = await _ids()
    values = {"t": tenant, "u": user, "status": "running", "count": 1, "deleted": False}
    first = await sql(_LIST, **values, started=STARTED)
    async with async_session_factory() as session:
        with pytest.raises(DBAPIError):  # a second running list of the tenant
            await session.execute(text(_LIST), {**values, "started": STARTED})
        await session.rollback()
    for overrides in (
        {"status": "bitti", "started": None},
        {"status": "completed", "started": STARTED},
        {"status": "completed", "started": None, "count": 0},
        {"status": "completed", "started": None, "deleted": True},
    ):
        async with async_session_factory() as session:
            with pytest.raises(DBAPIError):
                await session.execute(text(_LIST), {**values, **overrides})
            await session.rollback()
    list_id = first[0][0]
    await sql(
        "INSERT INTO term_list_item (term_list_id, position, term) VALUES (:l, 1, 'kart')",
        l=list_id,
    )
    for statement in (
        "UPDATE term_list_item SET flow = 'analyst' WHERE term_list_id = :l",
        (
            "UPDATE term_list_item SET answer = '{}'::jsonb, flow = 'analyst', error_code = 'x' "
            "WHERE term_list_id = :l"
        ),
        "UPDATE term_list_item SET position = 0 WHERE term_list_id = :l",
    ):
        async with async_session_factory() as session:
            with pytest.raises(DBAPIError):
                await session.execute(text(statement), {"l": list_id})
            await session.rollback()
    await sql("DELETE FROM term_list WHERE term_list_id = :l", l=list_id)
    assert await sql("SELECT count(*) FROM term_list_item WHERE term_list_id = :l", l=list_id) == [
        (0,)
    ]


async def test_the_database_keeps_the_vote_rules(auth: AuthHarness) -> None:
    await auth.super_admin()
    tenant, user = await _ids()
    insert = (
        "INSERT INTO answer_vote (tenant_id, voter_id, query_text, text_key, scope, table_key, "
        "vote, dictionary_version) VALUES (:t, :u, :q, 'k', :scope, :table, :vote, 'v')"
    )
    good = {"t": tenant, "u": user, "q": "soru", "scope": "table", "table": "A.B.C", "vote": "up"}
    await sql(insert, **good)
    for overrides in (
        {"scope": "object"},
        {"vote": "maybe"},
        {"table": None},
        {"scope": "answer"},
        {"q": ""},
    ):
        async with async_session_factory() as session:
            with pytest.raises(DBAPIError):
                await session.execute(text(insert), {**good, **overrides})
            await session.rollback()
    await sql("DELETE FROM answer_vote")


def test_the_migrations_go_down_and_up(migrated_database: None) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    tables = {"term_list", "term_list_item", "answer_vote"}

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
        command.downgrade(config, "202610090002")
        assert asyncio.run(present()) & tables == {"answer_vote"}
        command.downgrade(config, "202610090001")
        assert tables.isdisjoint(asyncio.run(present()))
    finally:
        command.upgrade(config, "head")
    assert tables <= asyncio.run(present())
    command.check(config)
