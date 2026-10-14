"""The migrated visitor table and the account-or-visitor owners (application-foundation
003-anonymous-visitor Veri ve geçiş, Decision 5).

visitor carries the mandatory block, a unique hash of the device id (never the id itself) and the
last address and host name. analysis_record, answer_vote and term_list belong to exactly one of an
account or a visitor and keep the address and host name of the moment; rows without either, or
with both, are refused. Comments are written (rules/43).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import async_session_factory, engine
from tests.integration.conftest import AuthHarness
from tests.integration.data_dictionary import sql
from tests.integration.test_data_dictionary_model import BLOCK, _columns, _scalar

pytestmark = pytest.mark.integration

ASKED = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
OWNED = {
    "analysis_record": ("asked_by", "asked_by_visitor_id"),
    "answer_vote": ("voter_id", "voter_visitor_id"),
    "term_list": ("owner_id", "owner_visitor_id"),
}


async def _comment(connection: object, table: str, column: str) -> str | None:
    return await _scalar(
        connection,  # type: ignore[arg-type]
        "SELECT col_description(CAST(:t AS regclass), attnum) FROM pg_attribute "
        "WHERE attrelid = CAST(:t AS regclass) AND attname = :c",
        t=table,
        c=column,
    )


async def test_the_visitor_table_its_block_and_comments(
    migrated_database: None,
) -> None:
    async with engine.connect() as connection:
        columns = await _columns(connection, "visitor")
        for column, kind in BLOCK.items():
            assert columns[column] == kind, column
        assert {
            "visitor_id",
            "public_id",
            "tenant_id",
            "device_key",
            "first_seen_at",
            "last_seen_at",
            "last_address",
            "last_host",
        } <= set(columns)
        assert "device_id" not in columns
        assert await _scalar(
            connection,
            "SELECT obj_description(CAST('visitor' AS regclass), 'pg_class')",
        )
        for column in ("device_key", "last_address", "last_host", "public_id"):
            assert await _comment(connection, "visitor", column), column
        for table, (account, visitor) in OWNED.items():
            found = await _columns(connection, table)
            assert {account, visitor, "client_address", "client_host"} <= set(found), table
            for column in (account, visitor, "client_address", "client_host"):
                assert await _comment(connection, table, column), (table, column)


async def _visitor(tenant: int) -> int:
    rows = await sql(
        "INSERT INTO visitor (public_id, tenant_id, device_key, first_seen_at, last_seen_at, "
        "last_address) VALUES (gen_random_uuid()::text, :t, md5(random()::text) || md5(random()::text), "
        "now(), now(), '10.0.0.9') RETURNING visitor_id",
        t=tenant,
    )
    return int(rows[0][0])


async def test_a_row_belongs_to_exactly_one_account_or_visitor(
    auth: AuthHarness,
) -> None:
    await auth.super_admin()
    tenant, user = (
        int(value)
        for value in (await sql("SELECT home_tenant_id, user_id FROM app_user LIMIT 1"))[0]
    )
    visitor = await _visitor(tenant)
    record = (
        "INSERT INTO analysis_record (public_id, tenant_id, asked_by, asked_by_visitor_id, "
        "client_address, client_host, state, asked_at, query, fresh, origin) VALUES "
        "(gen_random_uuid()::text, :t, :u, :v, '10.0.0.9', 'pc-1', 'queued', :at, 'soru', false, "
        "'question')"
    )
    vote = (
        "INSERT INTO answer_vote (tenant_id, voter_id, voter_visitor_id, client_address, "
        "query_text, text_key, scope, vote, dictionary_version) VALUES (:t, :u, :v, '10.0.0.9', "
        "'soru', 'k', 'answer', 'up', 'v')"
    )
    term_list = (
        "INSERT INTO term_list (public_id, tenant_id, owner_id, owner_visitor_id, client_address, "
        "file_name, header, status, term_count, dictionary_version, is_deleted) VALUES "
        "(gen_random_uuid()::text, :t, :u, :v, '10.0.0.9', 'a.xlsx', 'Terim', 'completed', 1, "
        "'v', false)"
    )
    for statement in (record, vote, term_list):
        for owner in ({"u": user, "v": None}, {"u": None, "v": visitor}):
            await sql(statement, t=tenant, at=ASKED, **owner)
        for owner in ({"u": user, "v": visitor}, {"u": None, "v": None}):
            async with async_session_factory() as session:
                with pytest.raises(DBAPIError):
                    await session.execute(text(statement), {"t": tenant, "at": ASKED, **owner})
                await session.rollback()
    await sql("DELETE FROM analysis_record WHERE asked_at = :at", at=ASKED)
    await sql("DELETE FROM answer_vote")
    await sql("DELETE FROM term_list")
    await sql("DELETE FROM visitor WHERE visitor_id = :v", v=visitor)


async def test_the_device_key_is_unique(auth: AuthHarness) -> None:
    await auth.super_admin()
    tenant = int((await sql("SELECT tenant_id FROM tenant LIMIT 1"))[0][0])
    first = await _visitor(tenant)
    key = (await sql("SELECT device_key FROM visitor WHERE visitor_id = :v", v=first))[0][0]
    async with async_session_factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO visitor (public_id, tenant_id, device_key, first_seen_at, "
                    "last_seen_at, last_address) VALUES (gen_random_uuid()::text, :t, :k, now(), "
                    "now(), '10.0.0.9')"
                ),
                {"t": tenant, "k": key},
            )
        await session.rollback()
    await sql("DELETE FROM visitor WHERE visitor_id = :v", v=first)
