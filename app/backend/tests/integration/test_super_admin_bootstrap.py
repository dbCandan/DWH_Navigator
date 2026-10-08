"""Start-up creation and operator reset of the super admin on PostgreSQL.

application-foundation/PRDs/001-user-accounts Requirement 17 and 18, Decision 18 and 21: the
backend creates the configured super admin once, through the same path as the operator command;
its first login asks for a new password; an existing account is never changed; a weak password
creates nothing and never reaches a log; concurrent attempts create one account; the command
resets the password, activation and role and never takes the start-up password.
"""

import asyncio
import io
import sys
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text, update

from app.core.config import Settings, get_settings
from app.db.session import async_session_factory
from app.domain.models.role import Role, UserRole
from app.domain.models.user import User
from app.infrastructure.repositories.user_repository import UserRepository
from app.scripts import create_super_admin
from app.services.super_admin_service import (
    BootstrapOutcome,
    SuperAdminRejected,
    bootstrap_super_admin,
    ensure_super_admin,
)
from tests.integration.conftest import AuthHarness, RecordingHandler, new_password

pytestmark = pytest.mark.integration


def _name() -> str:
    return f"admin-{uuid4().hex[:10]}"


def _settings(username: str, password: str | None) -> Settings:
    return get_settings().model_copy(
        update={
            "environment": "staging",
            "bootstrap_super_admin_username": username,
            "bootstrap_super_admin_email": "",
            "bootstrap_super_admin_password": SecretStr(password) if password else None,
        }
    )


async def _account(username: str) -> User | None:
    async with async_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is not None:
            session.expunge(user)
        return user


async def _changes(username: str) -> list[tuple[Any, ...]]:
    async with async_session_factory() as session:
        rows = await session.execute(
            text(
                "SELECT c.changed_field, c.old_value, c.new_value, "
                "c.actor_user_id = c.target_user_id "
                "FROM app_user_change c JOIN app_user u ON u.user_id = c.target_user_id "
                "WHERE u.username = :name ORDER BY c.app_user_change_id"
            ),
            {"name": username},
        )
        return [tuple(row) for row in rows.all()]


async def _roles(username: str) -> tuple[str, ...]:
    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.username == username))).scalar_one()
        return await UserRepository(session).role_codes(user)


async def test_the_start_creates_the_super_admin_once_and_its_first_login_asks_for_a_password(
    auth: AuthHarness, recorded_logs: RecordingHandler
) -> None:
    username = _name()
    password = new_password()
    settings = _settings(username, password)

    first = await bootstrap_super_admin(async_session_factory, settings)
    second = await bootstrap_super_admin(async_session_factory, settings)

    assert (first, second) == (BootstrapOutcome.CREATED, BootstrapOutcome.EXISTS)
    account = await _account(username)
    assert account is not None
    assert account.is_active and account.password_change_required
    assert account.one_time_password_expires_at is None
    assert account.display_name == "Süper yönetici"
    assert await _roles(username) == ("super_admin",)
    assert await _changes(username) == [("account", None, "super_admin", True)]
    events = recorded_logs.events("auth.super_admin.bootstrap")
    assert [event["outcome"] for event in events] == ["created", "exists"]
    assert all(event["user_public_id"] == account.public_id for event in events)
    assert all(event["super_admin"] is True for event in events)
    assert password not in recorded_logs.rendered()

    login = await auth.login(username, password)
    assert login.status_code == 403
    assert login.json()["detail"]["code"] == "password_change_required"
    session = await auth.activate(username, password)
    assert session.body["user"]["is_super_admin"] is True
    assert session.body["user"]["role"] == "super_admin"


async def test_an_existing_account_is_never_changed_by_the_start(auth: AuthHarness) -> None:
    username = _name()
    first_password = new_password()
    await bootstrap_super_admin(async_session_factory, _settings(username, first_password))
    await auth.activate(username, first_password)
    async with async_session_factory() as session:
        await session.execute(update(User).where(User.username == username).values(is_active=False))
        await session.commit()
    before = await _account(username)

    outcome = await bootstrap_super_admin(
        async_session_factory, _settings(username, new_password())
    )

    assert outcome is BootstrapOutcome.EXISTS
    after = await _account(username)
    assert before is not None and after is not None
    assert after.password_hash == before.password_hash
    assert after.is_active is False
    assert after.password_change_required is False
    assert after.updated_at == before.updated_at
    assert len(await _changes(username)) == 2  # account + the chosen password, nothing new


async def test_an_account_with_another_role_is_reported_and_untouched(
    auth: AuthHarness, recorded_logs: RecordingHandler
) -> None:
    admin = await auth.super_admin()
    opened = await auth.open_account(admin, "kullanici")

    outcome = await bootstrap_super_admin(
        async_session_factory, _settings(opened.username, new_password())
    )

    assert outcome is BootstrapOutcome.EXISTS
    (event,) = recorded_logs.events("auth.super_admin.bootstrap")
    assert event["super_admin"] is False
    assert await _roles(opened.username) == ("kullanici",)


@pytest.mark.parametrize(
    "password",
    ("kisa-parola", "passwordpassword", "dwhnavigator yonetici parolasi", "a" * 30),
    ids=("too_short", "common", "product_name", "repeated"),
)
async def test_a_weak_password_creates_nothing_and_is_never_logged(
    auth: AuthHarness, recorded_logs: RecordingHandler, password: str
) -> None:
    username = _name()

    outcome = await bootstrap_super_admin(async_session_factory, _settings(username, password))

    assert outcome is BootstrapOutcome.REJECTED
    assert await _account(username) is None
    (event,) = recorded_logs.events("auth.super_admin.bootstrap")
    assert event == {
        "event": "auth.super_admin.bootstrap",
        "outcome": "rejected",
        "reason": "password_policy",
    }
    assert password not in recorded_logs.rendered()


async def test_concurrent_start_and_command_create_one_account(auth: AuthHarness) -> None:
    username = _name()
    password = new_password()

    async def command() -> object:
        async with async_session_factory() as session:
            try:
                return await ensure_super_admin(
                    session, username=username, password=password, reset_existing=False
                )
            except SuperAdminRejected as rejected:  # pragma: no cover - not expected
                return rejected

    results = await asyncio.gather(
        bootstrap_super_admin(async_session_factory, _settings(username, password)),
        bootstrap_super_admin(async_session_factory, _settings(username, password)),
        command(),
    )

    created = [result for result in results if result is BootstrapOutcome.CREATED]
    created += [r for r in results if getattr(r, "created", False)]
    assert len(created) == 1
    async with async_session_factory() as session:
        rows = (await session.execute(select(User).where(User.username == username))).all()
    assert len(rows) == 1
    assert len(await _changes(username)) == 1


async def test_the_command_resets_password_activation_and_role_and_ends_sessions(
    auth: AuthHarness,
) -> None:
    admin = await auth.super_admin()
    # Drop the account's super admin assignment and deactivate it, as a broken state.
    async with async_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.username == admin.username))
        ).scalar_one()
        role_id = (
            await session.execute(select(Role.role_id).where(Role.code == "super_admin"))
        ).scalar_one()
        await session.execute(
            update(UserRole)
            .where(UserRole.user_id == user.user_id, UserRole.role_id == role_id)
            .values(is_deleted=True)
        )
        user.is_active = False
        await session.commit()

    reset_password = new_password()
    async with async_session_factory() as session:
        result = await ensure_super_admin(session, username=admin.username, password=reset_password)

    assert result.created is False and result.is_super_admin is True
    account = await _account(admin.username)
    assert account is not None
    assert account.is_active and account.password_change_required
    assert account.one_time_password_expires_at is None
    assert await _roles(admin.username) == ("super_admin",)
    assert await _changes(admin.username) == [
        ("account", None, "super_admin", True),
        ("password", None, "changed", True),
        ("password", None, "reset", True),
        ("active", "false", "true", True),
        ("role", None, "super_admin", True),
    ]
    refused = await auth.refresh(admin.refresh_token)
    assert refused.status_code == 401
    assert (await auth.login(admin.username, admin.password)).status_code == 401
    assert (await auth.login(admin.username, reset_password)).status_code == 403
    await auth.activate(admin.username, reset_password)


async def test_the_command_refuses_the_current_password_and_an_invalid_name(
    auth: AuthHarness,
) -> None:
    admin = await auth.super_admin()
    async with async_session_factory() as session:
        with pytest.raises(SuperAdminRejected) as reused:
            await ensure_super_admin(session, username=admin.username, password=admin.password)
    assert reused.value.reason == "password_policy"
    async with async_session_factory() as session:
        with pytest.raises(SuperAdminRejected) as invalid:
            await ensure_super_admin(session, username="Süper Admin", password=new_password())
    assert invalid.value.reason == "invalid_username"


async def test_the_command_line_reads_stdin_and_ignores_the_start_up_password(
    auth: AuthHarness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    username = _name()
    typed = new_password()
    start_up = new_password()
    monkeypatch.setenv("DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD", start_up)
    monkeypatch.setenv("DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_USERNAME", username)
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{typed}\n"))
    monkeypatch.setattr(sys, "argv", ["create_super_admin", "--password-stdin", "--email", ""])
    get_settings.cache_clear()
    try:
        await asyncio.to_thread(create_super_admin.main)
    finally:
        get_settings.cache_clear()

    output = capsys.readouterr().out
    assert "açıldı" in output and typed not in output and start_up not in output
    assert (await auth.login(username, start_up)).status_code == 401
    assert (await auth.login(username, typed)).status_code == 403
