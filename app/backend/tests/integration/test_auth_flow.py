"""Login, first password, password change, refresh and logout against PostgreSQL.

application-foundation/PRDs/001-user-accounts Requirement 1, 3, 4 and 6-9, Acceptance 1.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from httpx import Response
from sqlalchemy import func, select, update

from app.core.login_throttle import ADDRESS_MAX_FAILURES, NAME_ADDRESS_MAX_FAILURES
from app.core.security import refresh_token_digest
from app.db.session import async_session_factory
from app.domain.models.refresh_session import RefreshSession
from app.domain.models.user import User
from app.domain.models.user_change import UserChange
from tests.integration.conftest import (
    CLIENT_ADDRESS,
    AuthHarness,
    RecordingHandler,
    new_name,
    new_password,
)

pytestmark = pytest.mark.integration


async def _user_row(username: str) -> User:
    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.username == username))).scalar_one()
        session.expunge(user)
        return user


async def _set_user(username: str, **values: object) -> None:
    async with async_session_factory() as session:
        await session.execute(update(User).where(User.username == username).values(**values))
        await session.commit()


def _error(response: Response) -> tuple[int, str]:
    body = response.json()
    return int(response.status_code), str(body["detail"]["code"])


async def test_a_new_account_must_set_its_password_before_any_session(auth: AuthHarness) -> None:
    admin = await auth.super_admin()
    opened = await auth.open_account(admin, "kullanici")

    first = await auth.login(opened.username, opened.one_time_password)
    assert _error(first) == (403, "password_change_required")
    assert "set-cookie" not in first.headers
    assert "access_token" not in first.text

    wrong = await auth.login(opened.username, "yanlis " + opened.one_time_password)
    assert _error(wrong) == (401, "invalid_credentials")

    session = await auth.activate(opened.username, opened.one_time_password)
    assert session.body["user"]["role"] == "kullanici"
    assert session.body["token_type"] == "bearer"
    assert session.body["expires_in"] == 15 * 60
    claims = jwt.decode(session.access_token, options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert claims["roles"] == ["kullanici"]

    # The one-time password stopped working; the person's own password logs in.
    assert _error(await auth.login(opened.username, opened.one_time_password)) == (
        401,
        "invalid_credentials",
    )
    again = await auth.sign_in(opened.username, session.password)
    me = await auth.client.get(f"{auth.prefix}/auth/me", headers=auth.headers(again))
    assert me.status_code == 200, me.text
    assert me.json()["public_id"] == opened.public_id
    assert me.json()["display_name"] == "Ayşe Işık"
    assert me.json()["role"] == "kullanici"
    assert me.json()["is_super_admin"] is False

    user = await _user_row(opened.username)
    assert user.password_change_required is False
    assert user.one_time_password_expires_at is None
    assert user.password_changed_at is not None
    assert user.last_login_at is not None


async def test_wrong_password_and_unknown_name_answer_alike(auth: AuthHarness) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)

    wrong = await auth.login(account.username, new_password())
    unknown = await auth.login(new_name("yok"), new_password())

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.headers["www-authenticate"] == unknown.headers["www-authenticate"] == "Bearer"


async def test_login_normalizes_the_name_and_ignores_the_e_mail(auth: AuthHarness) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    await _set_user(account.username, email=f"{account.username}@example.test")

    upper = await auth.login(f"  {account.username.upper()}  ", account.password)
    assert upper.status_code == 200, upper.text
    by_email = await auth.login(f"{account.username}@example.test", account.password)
    assert _error(by_email) == (401, "invalid_credentials")
    # The password is never trimmed.
    assert _error(await auth.login(account.username, f" {account.password} ")) == (
        401,
        "invalid_credentials",
    )


async def test_an_inactive_account_is_told_so_only_with_the_right_password(
    auth: AuthHarness,
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    await _set_user(account.username, is_active=False)

    assert _error(await auth.login(account.username, account.password)) == (403, "user_inactive")
    assert _error(await auth.login(account.username, new_password())) == (
        401,
        "invalid_credentials",
    )
    assert _error(
        await auth.change_password(account.username, account.password, new_password())
    ) == (403, "user_inactive")


async def test_an_expired_one_time_password_is_refused_for_login_and_change(
    auth: AuthHarness,
) -> None:
    admin = await auth.super_admin()
    opened = await auth.open_account(admin)
    expires = datetime.fromisoformat(opened.body["one_time_password_expires_at"])
    assert timedelta(hours=71, minutes=59) < expires - datetime.now(UTC) <= timedelta(hours=72)
    await _set_user(
        opened.username, one_time_password_expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )

    login = await auth.login(opened.username, opened.one_time_password)
    assert _error(login) == (401, "one_time_password_expired")
    change = await auth.change_password(opened.username, opened.one_time_password, new_password())
    assert _error(change) == (401, "one_time_password_expired")
    # Only the person who knows the right one-time password learns that it expired.
    assert _error(await auth.login(opened.username, new_password())) == (
        401,
        "invalid_credentials",
    )


@pytest.mark.parametrize(
    ("make_new", "reason_text"),
    (
        (lambda current, name: "kisa parola", "en az 15"),
        (lambda current, name: "x" * 129, "en çok 128"),
        (lambda current, name: "passwordpassword", "yaygın"),
        (lambda current, name: f"benim adim {name} tamam", "kullanıcı adınızı"),
        (lambda current, name: f"güzel bir IŞIK sabahı {current[:3]}", "kullanıcı adınızı"),
        (lambda current, name: current, "şimdiki"),
    ),
    ids=("too_short", "too_long", "common", "username", "display_name", "reused"),
)
async def test_the_new_password_must_meet_the_policy(
    auth: AuthHarness,
    recorded_logs: RecordingHandler,
    make_new: object,
    reason_text: str,
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    candidate = make_new(account.password, account.username)  # type: ignore[operator]

    response = await auth.change_password(account.username, account.password, candidate)

    assert _error(response) == (422, "password_policy")
    assert reason_text in response.json()["detail"]["message"]
    assert candidate not in response.text
    failed = recorded_logs.events("auth.password.change_failed")
    assert failed[-1]["reason"] == "password_policy"
    assert failed[-1]["policy_reason"] in {
        "too_short",
        "too_long",
        "common",
        "contains_account_name",
        "reused",
    }
    assert account.username not in recorded_logs.rendered()
    # The old password still works: nothing changed.
    assert (await auth.login(account.username, account.password)).status_code == 200


async def test_a_voluntary_change_closes_sessions_and_writes_a_value_free_row(
    auth: AuthHarness, recorded_logs: RecordingHandler
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    other_session = await auth.sign_in(account.username, account.password)
    password = new_password()

    changed = await auth.change_password(account.username, account.password, password)

    assert changed.status_code == 200, changed.text
    assert set(changed.json()) == {"access_token", "token_type", "expires_in", "user"}
    assert _error(await auth.refresh(other_session.refresh_token)) == (401, "session_revoked")
    assert (await auth.refresh(auth.refresh_cookie(changed))).status_code == 200
    # A repeated request fails: its current password is no longer current.
    repeated = await auth.change_password(account.username, account.password, password)
    assert _error(repeated) == (401, "invalid_credentials")
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(UserChange.changed_field, UserChange.old_value, UserChange.new_value)
                .join(User, User.user_id == UserChange.target_user_id)
                .where(User.username == account.username, UserChange.changed_field == "password")
                .order_by(UserChange.app_user_change_id)
            )
        ).all()
    assert [tuple(row) for row in rows] == [
        ("password", None, "changed"),
        ("password", None, "changed"),
    ]
    kinds = [event["kind"] for event in recorded_logs.events("auth.password.changed")]
    assert kinds[-2:] == ["initial", "voluntary"]


async def test_concurrent_changes_of_one_account_queue_and_only_one_wins(
    auth: AuthHarness,
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)

    results = await asyncio.gather(
        auth.client.post(
            f"{auth.prefix}/auth/password",
            json={
                "username": account.username,
                "current_password": account.password,
                "new_password": new_password(),
            },
        ),
        auth.client.post(
            f"{auth.prefix}/auth/password",
            json={
                "username": account.username,
                "current_password": account.password,
                "new_password": new_password(),
            },
        ),
    )

    assert sorted(response.status_code for response in results) == [200, 401]


async def test_refresh_rotates_reads_the_current_role_and_detects_reuse(
    auth: AuthHarness, recorded_logs: RecordingHandler
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin, "kullanici")

    rotated = await auth.refresh(account.refresh_token)
    assert rotated.status_code == 200, rotated.text
    new_token = auth.refresh_cookie(rotated)
    assert new_token != account.refresh_token
    assert rotated.json()["user"]["role"] == "kullanici"

    # The used token comes back: its whole family ends and an audit event is written.
    reuse = await auth.refresh(account.refresh_token)
    assert _error(reuse) == (401, "session_revoked")
    assert _error(await auth.refresh(new_token)) == (401, "session_revoked")
    (event,) = recorded_logs.events("auth.session.reuse_detected")
    assert event["user_public_id"] == account.public_id
    assert event["session_family"]


async def _session_row(refresh_token: str) -> RefreshSession:
    async with async_session_factory() as session:
        record = (
            await session.execute(
                select(RefreshSession).where(
                    RefreshSession.token_sha256 == refresh_token_digest(refresh_token)
                )
            )
        ).scalar_one()
        session.expunge(record)
        return record


async def _move_session(refresh_token: str, **values: object) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.token_sha256 == refresh_token_digest(refresh_token))
            .values(**values)
        )
        await session.commit()


async def test_refresh_expires_when_idle_or_after_the_absolute_limit(auth: AuthHarness) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    idle = await auth.sign_in(account.username, account.password)
    absolute = await auth.sign_in(account.username, account.password)
    record = await _session_row(idle.refresh_token)
    assert record.absolute_expires_at - record.created_at <= timedelta(hours=8, seconds=5)
    assert record.absolute_expires_at - record.created_at >= timedelta(hours=7, minutes=59)
    assert record.idle_expires_at - record.created_at <= timedelta(minutes=60, seconds=5)

    # A rotation keeps the family's absolute limit and starts a new idle period.
    rotated = await auth.refresh(absolute.refresh_token)
    successor = await _session_row(auth.refresh_cookie(rotated))
    original = await _session_row(absolute.refresh_token)
    assert successor.absolute_expires_at == original.absolute_expires_at
    assert successor.family_id == original.family_id

    now = datetime.now(UTC)
    await _move_session(idle.refresh_token, idle_expires_at=now - timedelta(seconds=1))
    await _move_session(
        auth.refresh_cookie(rotated),
        idle_expires_at=now - timedelta(seconds=2),
        absolute_expires_at=now - timedelta(seconds=1),
    )

    assert _error(await auth.refresh(idle.refresh_token)) == (401, "session_expired")
    assert _error(await auth.refresh(auth.refresh_cookie(rotated))) == (401, "session_expired")
    assert _error(await auth.refresh(None)) == (401, "session_expired")
    assert _error(await auth.refresh("bilinmeyen-belirtec")) == (401, "session_expired")


async def test_logout_ends_the_session_on_the_server(
    auth: AuthHarness, recorded_logs: RecordingHandler
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)

    out = await auth.logout(account.refresh_token)

    assert out.status_code == 204
    cleared = out.headers["set-cookie"]
    assert "dwhnavigator_refresh=" in cleared and "Max-Age=0" in cleared
    assert _error(await auth.refresh(account.refresh_token)) == (401, "session_revoked")
    assert (await auth.logout(account.refresh_token)).status_code == 204
    assert (await auth.logout(None)).status_code == 204
    assert recorded_logs.events("auth.logout")[0]["user_public_id"] == account.public_id


async def test_the_refresh_cookie_is_secure_http_only_strict_and_path_scoped(
    auth: AuthHarness,
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    response = await auth.login(account.username, account.password)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("dwhnavigator_refresh=")
    for attribute in ("Secure", "HttpOnly", "SameSite=strict", f"Path={auth.prefix}/auth"):
        assert attribute.lower() in cookie.lower(), attribute
    assert "Max-Age=" in cookie
    async with async_session_factory() as session:
        stored = (await session.execute(select(RefreshSession.token_sha256))).scalars().all()
    assert auth.refresh_cookie(response) not in stored


async def test_failed_logins_and_password_changes_share_the_limits(
    auth: AuthHarness, recorded_logs: RecordingHandler
) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    for _ in range(NAME_ADDRESS_MAX_FAILURES - 1):
        assert (await auth.login(account.username, new_password())).status_code == 401
    wrong_change = await auth.change_password(account.username, new_password(), new_password())
    assert wrong_change.status_code == 401

    # The limit is reached: even the right password is not checked any more.
    blocked = await auth.login(account.username, account.password)
    assert _error(blocked) == (429, "rate_limited")
    assert int(blocked.headers["retry-after"]) > 0
    change = await auth.change_password(account.username, account.password, new_password())
    assert _error(change) == (429, "rate_limited")
    event = recorded_logs.events("auth.login.rate_limited")[0]
    assert event["limit"] == "user" and event["name_digest"]
    assert account.username not in recorded_logs.rendered()

    # After the window (a fresh process here) the person logs in again; no permanent lock exists.
    auth.limiter.clear()
    assert (await auth.login(account.username, account.password)).status_code == 200


async def test_a_successful_login_resets_the_name_counter(auth: AuthHarness) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    for _ in range(NAME_ADDRESS_MAX_FAILURES - 1):
        assert (await auth.login(account.username, new_password())).status_code == 401
    assert (await auth.login(account.username, account.password)).status_code == 200
    for _ in range(NAME_ADDRESS_MAX_FAILURES - 1):
        assert (await auth.login(account.username, new_password())).status_code == 401
    assert (await auth.login(account.username, account.password)).status_code == 200


async def test_the_address_limit_counts_every_name_from_one_address(auth: AuthHarness) -> None:
    for index in range(ADDRESS_MAX_FAILURES):
        response = await auth.login(f"kimse.{index}", new_password())
        assert response.status_code == 401
    assert _error(await auth.login("baska.biri", new_password())) == (429, "rate_limited")


async def test_forwarded_for_counts_only_from_the_trusted_ingress(auth: AuthHarness) -> None:
    auth.use_settings(trusted_proxy_cidrs=f"{CLIENT_ADDRESS}/32")
    for index in range(ADDRESS_MAX_FAILURES):
        response = await auth.login(
            f"kimse.{index}", new_password(), headers={"x-forwarded-for": "198.51.100.7"}
        )
        assert response.status_code == 401
    blocked = await auth.login(
        "baska.biri", new_password(), headers={"x-forwarded-for": "198.51.100.7"}
    )
    assert blocked.status_code == 429
    other = await auth.login(
        "baska.biri", new_password(), headers={"x-forwarded-for": "198.51.100.8"}
    )
    assert other.status_code == 401

    # Without the trust the header is ignored and the peer address counts.
    auth.use_settings(trusted_proxy_cidrs="")
    auth.limiter.clear()
    for index in range(ADDRESS_MAX_FAILURES):
        await auth.login(
            f"kimse.{index}", new_password(), headers={"x-forwarded-for": f"203.0.113.{index}"}
        )
    assert (await auth.login("baska.biri", new_password())).status_code == 429


async def test_me_reads_the_account_and_refuses_a_deactivated_one(auth: AuthHarness) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin, "yonetici")
    me = await auth.client.get(f"{auth.prefix}/auth/me", headers=auth.headers(account))
    assert me.status_code == 200
    assert me.json()["role"] == "yonetici"
    assert UUID(me.json()["tenant_id"]) == UUID(account.tenant_id)

    await _set_user(account.username, is_active=False)
    gone = await auth.client.get(f"{auth.prefix}/auth/me", headers=auth.headers(account))
    assert _error(gone) == (401, "not_authenticated")


async def test_ended_sessions_are_deleted_seven_days_later(auth: AuthHarness) -> None:
    admin = await auth.super_admin()
    account = await auth.account(admin)
    async with async_session_factory() as session:
        await session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id
                == select(User.user_id).where(User.username == account.username).scalar_subquery()
            )
            .values(
                revoked_at=datetime.now(UTC) - timedelta(days=8),
                revoke_reason="logout",
                idle_expires_at=datetime.now(UTC) - timedelta(days=8),
                absolute_expires_at=datetime.now(UTC) - timedelta(days=8),
            )
        )
        await session.commit()

    # Any login purges rows ended more than seven days ago.
    await auth.sign_in(account.username, account.password)
    async with async_session_factory() as session:
        remaining = (
            await session.execute(
                select(func.count())
                .select_from(RefreshSession)
                .where(
                    RefreshSession.user_id
                    == select(User.user_id)
                    .where(User.username == account.username)
                    .scalar_subquery()
                )
            )
        ).scalar_one()
    assert remaining == 1
