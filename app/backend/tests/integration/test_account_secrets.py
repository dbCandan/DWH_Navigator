"""Passwords and one-time passwords never leak.

application-foundation/PRDs/001-user-accounts Decision 1 and the "Sızıntı" item of the test
strategy: a marked password and the generated one-time password appear in no log line, in no
database column except as a hash, in no API response except the opening and reset responses, and
in no span or metric.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.session import async_session_factory
from tests.fakes.telemetry import TelemetryCapture
from tests.integration.conftest import AuthHarness, RecordingHandler

pytestmark = pytest.mark.integration


async def _database_text() -> str:
    """Every text value of the account tables, hashes included, as one searchable string."""

    async with async_session_factory() as session:
        parts: list[str] = []
        for table in ("app_user", "app_user_change", "auth_refresh_session", "app_user_role"):
            rows = await session.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))
            parts.extend(str(row[0]) for row in rows.all())
    return "\n".join(parts)


async def test_marked_passwords_never_leave_their_one_allowed_place(
    auth: AuthHarness, recorded_logs: RecordingHandler, telemetry_capture: TelemetryCapture
) -> None:
    marker = f"GIZLI{uuid4().hex}"
    marked_password = f"isaretli {marker} parola"
    admin = await auth.super_admin()
    opened = await auth.open_account(admin)
    responses = []

    first = await auth.login(opened.username, opened.one_time_password)
    responses.append(first)
    changed = await auth.change_password(opened.username, opened.one_time_password, marked_password)
    responses.append(changed)
    assert changed.status_code == 200, changed.text
    responses.append(await auth.login(opened.username, marked_password))
    responses.append(await auth.login(opened.username, f"{marked_password} yanlis"))
    responses.append(
        await auth.client.get(
            f"{auth.prefix}/admin/users", params={"q": opened.username}, headers=auth.headers(admin)
        )
    )
    reset = await auth.client.post(
        f"{auth.prefix}/admin/users/{opened.public_id}/password-reset", headers=auth.headers(admin)
    )
    reset_password = reset.json()["one_time_password"]
    responses.append(await auth.login(opened.username, reset_password))
    responses.append(
        await auth.change_password(opened.username, reset_password, f"{marked_password}!")
    )

    secrets = (marker, opened.one_time_password, reset_password)
    for response in responses:
        for secret in secrets:
            assert secret not in response.text
            assert secret not in str(response.headers)
    logs = recorded_logs.rendered()
    database = await _database_text()
    signals = telemetry_capture.everything()
    for secret in secrets:
        assert secret not in logs
        assert secret not in database
        assert secret not in signals
    # The hash is the only stored form of the passwords.
    assert "$argon2" in database
    # The username is replaced by its keyed digest in failure events.
    assert opened.username not in logs
