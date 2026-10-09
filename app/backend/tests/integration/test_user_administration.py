"""Super-admin account administration against PostgreSQL.

application-foundation/PRDs/001-user-accounts Requirement 2, 5 and 10, Decision 20 and the API
contract's repetition and concurrency rules.
"""

import asyncio
import re
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.security import ONE_TIME_PASSWORD_ALPHABET
from app.db.session import async_session_factory
from app.domain.models.role import Role, UserRole
from app.domain.models.user import User
from app.domain.models.user_change import UserChange
from tests.integration.conftest import AuthHarness, RecordingHandler, SignedIn, new_name

pytestmark = pytest.mark.integration


def _error(response: Any) -> tuple[int, str]:
    return int(response.status_code), str(response.json()["detail"]["code"])


async def _changes(username: str) -> list[tuple[str, str | None, str]]:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(UserChange.changed_field, UserChange.old_value, UserChange.new_value)
                .join(User, User.user_id == UserChange.target_user_id)
                .where(User.username == username)
                .order_by(UserChange.app_user_change_id)
            )
        ).all()
    return [(str(row[0]), row[1], str(row[2])) for row in rows]


class Admin:
    def __init__(self, auth: AuthHarness, session: SignedIn) -> None:
        self.auth = auth
        self.session = session

    @property
    def base(self) -> str:
        return f"{self.auth.prefix}/admin/users"

    async def create(self, **body: Any) -> Any:
        return await self.auth.client.post(
            self.base, json=body, headers=self.auth.headers(self.session)
        )

    async def list(self, **params: Any) -> Any:
        return await self.auth.client.get(
            self.base, params=params, headers=self.auth.headers(self.session)
        )

    async def role(self, public_id: str, role: str) -> Any:
        return await self.auth.client.put(
            f"{self.base}/{public_id}/role",
            json={"role": role},
            headers=self.auth.headers(self.session),
        )

    async def active(self, public_id: str, active: object) -> Any:
        return await self.auth.client.put(
            f"{self.base}/{public_id}/active",
            json={"active": active},
            headers=self.auth.headers(self.session),
        )

    async def reset(self, public_id: str) -> Any:
        return await self.auth.client.post(
            f"{self.base}/{public_id}/password-reset", headers=self.auth.headers(self.session)
        )


@pytest.fixture
async def admin(auth: AuthHarness) -> Admin:
    return Admin(auth, await auth.super_admin())


async def test_opening_an_account_returns_the_one_time_password_once(
    auth: AuthHarness, admin: Admin, recorded_logs: RecordingHandler
) -> None:
    username = new_name()
    created = await admin.create(
        username=f"  {username.upper()} ", display_name="  Çağrı Öztürk ", role="yonetici"
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert set(body) == {"user", "one_time_password", "one_time_password_expires_at"}
    password = body["one_time_password"]
    assert re.fullmatch(f"[{ONE_TIME_PASSWORD_ALPHABET}]{{20}}", password)
    assert body["user"]["username"] == username
    assert body["user"]["display_name"] == "Çağrı Öztürk"
    assert body["user"]["role"] == "yonetici"
    assert body["user"]["active"] is True
    assert body["user"]["password_change_required"] is True
    assert body["user"]["last_login_at"] is None
    assert created.headers["cache-control"] == "no-store"

    listed = await admin.list(q=username)
    assert password not in listed.text
    (row,) = listed.json()["items"]
    assert set(row) == {
        "public_id",
        "username",
        "display_name",
        "role",
        "active",
        "password_change_required",
        "last_login_at",
        "created_at",
    }
    assert await _changes(username) == [("account", None, "yonetici")]
    (event,) = recorded_logs.events("admin.user.created")
    assert event["actor_public_id"] == admin.session.public_id
    assert event["target_public_id"] == body["user"]["public_id"]
    assert event["role"] == "yonetici"
    assert password not in recorded_logs.rendered()


@pytest.mark.parametrize(
    "body",
    (
        {"username": "ab", "display_name": "Ali Veli", "role": "kullanici"},
        {"username": "ayşe.k", "display_name": "Ayşe", "role": "kullanici"},
        {"username": "x" * 65, "display_name": "Ali Veli", "role": "kullanici"},
        {"username": "ali.veli", "display_name": "", "role": "kullanici"},
        {"username": "ali.veli", "display_name": "x" * 129, "role": "kullanici"},
        {"username": "ali.veli", "display_name": "Ali\x07Veli", "role": "kullanici"},
        {"username": "ali.veli", "display_name": "Ali Veli", "role": "super_admin"},
        {"username": "ali.veli", "display_name": "Ali Veli", "role": "admin"},
        {"username": "ali.veli", "display_name": "Ali Veli"},
    ),
)
async def test_invalid_account_values_are_422_without_echo(
    admin: Admin, body: dict[str, Any]
) -> None:
    response = await admin.create(**body)
    assert _error(response) == (422, "invalid_request")
    assert "ayşe.k" not in response.text and "Ali\x07Veli" not in response.text


async def test_a_taken_name_is_409_even_for_an_inactive_account(
    auth: AuthHarness, admin: Admin
) -> None:
    opened = await auth.open_account(admin.session)
    assert (await admin.active(opened.public_id, False)).status_code == 200

    again = await admin.create(username=opened.username, display_name="Başka", role="kullanici")
    assert _error(again) == (409, "username_taken")


async def test_two_parallel_openings_with_one_name_create_one_account(
    admin: Admin,
) -> None:
    username = new_name()
    results = await asyncio.gather(
        admin.create(username=username, display_name="Bir", role="kullanici"),
        admin.create(username=username, display_name="İki", role="kullanici"),
    )
    assert sorted(response.status_code for response in results) == [201, 409]
    async with async_session_factory() as session:
        count = len((await session.execute(select(User).where(User.username == username))).all())
    assert count == 1


async def test_role_changes_are_recorded_close_sessions_and_repeat_safely(
    auth: AuthHarness, admin: Admin, recorded_logs: RecordingHandler
) -> None:
    account = await auth.account(admin.session, "kullanici")

    changed = await admin.role(account.public_id, "yonetici")
    assert changed.status_code == 200 and changed.json() == {"role": "yonetici"}
    repeated = await admin.role(account.public_id, "yonetici")
    assert repeated.status_code == 200 and repeated.json() == {"role": "yonetici"}

    assert _error(await auth.refresh(account.refresh_token)) == (401, "session_revoked")
    relogin = await auth.sign_in(account.username, account.password)
    assert relogin.body["user"]["role"] == "yonetici"
    assert relogin.body["user"]["roles"] == ["yonetici"]
    assert await _changes(account.username) == [
        ("account", None, "kullanici"),
        ("password", None, "changed"),
        ("role", "kullanici", "yonetici"),
    ]
    (event,) = recorded_logs.events("admin.user.role_changed")
    assert (event["old_value"], event["new_value"]) == ("kullanici", "yonetici")


async def test_parallel_role_writes_queue_and_each_real_change_is_one_row(
    auth: AuthHarness, admin: Admin
) -> None:
    account = await auth.account(admin.session, "kullanici")

    results = await asyncio.gather(
        admin.role(account.public_id, "yonetici"),
        admin.role(account.public_id, "kullanici"),
        admin.role(account.public_id, "yonetici"),
    )

    assert {response.status_code for response in results} == {200}
    role_rows = [row for row in await _changes(account.username) if row[0] == "role"]
    async with async_session_factory() as session:
        held = (
            (
                await session.execute(
                    select(Role.code)
                    .join(UserRole, UserRole.role_id == Role.role_id)
                    .join(User, User.user_id == UserRole.user_id)
                    .where(User.username == account.username, UserRole.is_deleted.is_(False))
                )
            )
            .scalars()
            .all()
        )
    # Whatever the order, the rows chain from one value to the next and end at the held role.
    assert len(held) == 1
    previous = "kullanici"
    for _, old, new in role_rows:
        assert old == previous and new != old
        previous = new
    assert previous == held[0]


async def test_deactivation_blocks_login_and_refresh_and_reactivation_restores_login(
    auth: AuthHarness, admin: Admin
) -> None:
    account = await auth.account(admin.session)

    off = await admin.active(account.public_id, False)
    assert off.status_code == 200 and off.json() == {"active": False}
    assert (await admin.active(account.public_id, False)).json() == {"active": False}

    assert _error(await auth.login(account.username, account.password)) == (403, "user_inactive")
    assert _error(await auth.refresh(account.refresh_token)) == (401, "session_revoked")
    on = await admin.active(account.public_id, True)
    assert on.status_code == 200
    assert (await auth.login(account.username, account.password)).status_code == 200
    assert [row for row in await _changes(account.username) if row[0] == "active"] == [
        ("active", "true", "false"),
        ("active", "false", "true"),
    ]


async def test_reset_issues_a_new_one_time_password_and_ends_the_old_one(
    auth: AuthHarness, admin: Admin, recorded_logs: RecordingHandler
) -> None:
    account = await auth.account(admin.session)

    reset = await admin.reset(account.public_id)

    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert set(body) == {"one_time_password", "one_time_password_expires_at"}
    assert _error(await auth.login(account.username, account.password)) == (
        401,
        "invalid_credentials",
    )
    assert _error(await auth.login(account.username, body["one_time_password"])) == (
        403,
        "password_change_required",
    )
    assert _error(await auth.refresh(account.refresh_token)) == (401, "session_revoked")
    second = (await admin.reset(account.public_id)).json()
    assert second["one_time_password"] != body["one_time_password"]
    assert _error(await auth.login(account.username, body["one_time_password"])) == (
        401,
        "invalid_credentials",
    )
    await auth.activate(account.username, second["one_time_password"])
    password_rows = [row for row in await _changes(account.username) if row[0] == "password"]
    assert password_rows == [
        ("password", None, "changed"),
        ("password", None, "reset"),
        ("password", None, "reset"),
        ("password", None, "changed"),
    ]
    assert len(recorded_logs.events("admin.user.password_reset")) == 2
    rendered = recorded_logs.rendered()
    assert body["one_time_password"] not in rendered and second["one_time_password"] not in rendered


async def test_super_admin_accounts_and_the_own_account_are_protected(
    auth: AuthHarness, admin: Admin
) -> None:
    other_admin = await auth.super_admin()

    for response in (
        await admin.role(other_admin.public_id, "kullanici"),
        await admin.active(other_admin.public_id, False),
        await admin.reset(other_admin.public_id),
    ):
        assert _error(response) == (409, "super_admin_protected")
    own = await admin.active(admin.session.public_id, False)
    assert _error(own) == (409, "own_account")
    assert _error(await admin.role(admin.session.public_id, "yonetici")) == (
        409,
        "super_admin_protected",
    )


async def test_unknown_accounts_and_invalid_values(admin: Admin) -> None:
    missing = str(uuid4())
    assert _error(await admin.role(missing, "yonetici")) == (404, "user_not_found")
    assert _error(await admin.active(missing, False)) == (404, "user_not_found")
    assert _error(await admin.reset(missing)) == (404, "user_not_found")
    assert _error(await admin.role(missing, "super_admin")) == (422, "invalid_request")
    assert _error(await admin.active(missing, "false")) == (422, "invalid_request")
    not_uuid = await admin.auth.client.put(
        f"{admin.base}/not-a-uuid/role",
        json={"role": "yonetici"},
        headers=admin.auth.headers(admin.session),
    )
    assert _error(not_uuid) == (422, "invalid_request")


async def test_the_list_pages_searches_and_orders_by_username(
    auth: AuthHarness, admin: Admin
) -> None:
    marker = uuid4().hex[:8]
    names = [f"{prefix}.{marker}" for prefix in ("zeki", "ali", "mert")]
    for name in names:
        created = await admin.create(username=name, display_name=f"Kişi {marker}", role="kullanici")
        assert created.status_code == 201

    first = await admin.list(q=marker, size=2, page=1)
    second = await admin.list(q=marker, size=2, page=2)
    assert first.status_code == 200
    assert first.json()["total"] == 3 and first.json()["page"] == 1 and first.json()["size"] == 2
    usernames = [item["username"] for item in first.json()["items"] + second.json()["items"]]
    assert usernames == sorted(names)
    by_display = await admin.list(q=f"kişi {marker}".upper())
    assert by_display.json()["total"] == 3
    assert _error(await admin.list(size=101)) == (422, "invalid_request")
    assert _error(await admin.list(page=0)) == (422, "invalid_request")
    assert (await admin.list(size=100)).status_code == 200


@pytest.mark.parametrize("role", ("kullanici", "yonetici"))
async def test_only_the_super_admin_manages_accounts(
    auth: AuthHarness, admin: Admin, role: str
) -> None:
    person = await auth.account(admin.session, role)
    headers = auth.headers(person)
    base = f"{auth.prefix}/admin/users"
    target = admin.session.public_id
    for response in (
        await auth.client.get(base, headers=headers),
        await auth.client.post(
            base,
            json={"username": new_name(), "display_name": "X", "role": "kullanici"},
            headers=headers,
        ),
        await auth.client.put(f"{base}/{target}/role", json={"role": "yonetici"}, headers=headers),
        await auth.client.put(f"{base}/{target}/active", json={"active": False}, headers=headers),
        await auth.client.post(f"{base}/{target}/password-reset", headers=headers),
    ):
        assert _error(response) == (403, "forbidden")
    anonymous = await auth.client.get(base, headers={auth.settings.tenant_header: person.tenant_id})
    assert _error(anonymous) == (401, "not_authenticated")


async def test_account_management_rereads_the_super_admin_from_the_database(
    auth: AuthHarness, admin: Admin
) -> None:
    # Decision 20: the token still says super admin, the database no longer does.
    async with async_session_factory() as session:
        user_id = (
            await session.execute(
                select(User.user_id).where(User.public_id == admin.session.public_id)
            )
        ).scalar_one()
        await session.execute(
            update(UserRole).where(UserRole.user_id == user_id).values(is_deleted=True)
        )
        await session.commit()
    assert _error(await admin.list()) == (403, "forbidden")
    assert _error(await admin.create(username=new_name(), display_name="X", role="kullanici")) == (
        403,
        "forbidden",
    )

    async with async_session_factory() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(is_active=False))
        await session.commit()
    assert _error(await admin.list()) == (401, "not_authenticated")
