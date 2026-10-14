"""The visitor on the main screen (application-foundation 003-anonymous-visitor Requirement 2-4,
6, Decision 1-4).

Main-screen endpoints answer without a session or a tenant header when a valid device id comes in
X-Device-Id; the backend opens one visitor per device id (only its SHA-256 is kept), refreshes
its last address, refuses a missing or malformed id with 400 and limits new visitors per address.
Administration endpoints keep their session and role: a device id opens none of them.
"""

import asyncio
import hashlib
import logging
from uuid import uuid4

import pytest

from app.services import visitors
from tests.integration.conftest import CLIENT_ADDRESS, AuthHarness, RecordingHandler
from tests.integration.data_dictionary import sql

pytestmark = pytest.mark.integration


def device() -> str:
    return str(uuid4())


async def _visitors(device_id: str) -> list[tuple[str, str]]:
    key = hashlib.sha256(device_id.encode()).hexdigest()
    rows = await sql("SELECT public_id, last_address FROM visitor WHERE device_key = :k", k=key)
    return [(str(r[0]), str(r[1])) for r in rows]


@pytest.fixture(autouse=True)
def _fresh_limits() -> None:
    visitors.reset_limits()


async def test_the_status_answers_a_visitor_without_a_session(
    auth: AuthHarness,
) -> None:
    await auth.super_admin()  # the platform tenant exists once an account does
    device_id = device()
    response = await auth.client.get(f"{auth.prefix}/status", headers={"X-Device-Id": device_id})
    assert response.status_code == 200, response.text
    found = await _visitors(device_id)
    assert len(found) == 1 and found[0][1] == CLIENT_ADDRESS
    again = await auth.client.get(f"{auth.prefix}/status", headers={"X-Device-Id": device_id})
    assert again.status_code == 200
    assert await _visitors(device_id) == found
    assert await sql("SELECT count(*) FROM visitor WHERE device_key = :k", k=device_id) == [
        (0,)
    ]  # the id itself is never stored


@pytest.mark.parametrize("header", [None, "", "kisi", "00000000-0000-1000-8000-000000000000"])
async def test_a_missing_or_malformed_device_id_is_refused(
    auth: AuthHarness, header: str | None
) -> None:
    headers = {} if header is None else {"X-Device-Id": header}
    response = await auth.client.get(f"{auth.prefix}/status", headers=headers)
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "device_id_required"


async def test_two_first_requests_open_one_visitor(auth: AuthHarness) -> None:
    await auth.super_admin()
    device_id = device()
    answers = await asyncio.gather(
        *(
            auth.client.get(f"{auth.prefix}/status", headers={"X-Device-Id": device_id})
            for _ in range(4)
        )
    )
    assert [a.status_code for a in answers] == [200] * 4
    assert len(await _visitors(device_id)) == 1


async def test_new_visitors_are_limited_per_address(auth: AuthHarness) -> None:
    await auth.super_admin()
    statuses = []
    for _ in range(visitors.NEW_VISITOR_LIMIT + 1):
        response = await auth.client.get(f"{auth.prefix}/status", headers={"X-Device-Id": device()})
        statuses.append(response.status_code)
    assert statuses[:-1] == [200] * visitors.NEW_VISITOR_LIMIT
    assert statuses[-1] == 429
    assert "retry-after" in {k.lower() for k in response.headers}


async def test_another_tenant_header_is_refused(auth: AuthHarness) -> None:
    await auth.super_admin()
    response = await auth.client.get(
        f"{auth.prefix}/status",
        headers={"X-Device-Id": device(), auth.settings.tenant_header: str(uuid4())},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "tenant_forbidden"


async def test_administration_stays_behind_the_session(auth: AuthHarness) -> None:
    await auth.super_admin()
    for path in (
        "/analysis-records",
        "/dictionary",
        "/admin/users",
        "/saved-answers/summary",
    ):
        response = await auth.client.get(f"{auth.prefix}{path}", headers={"X-Device-Id": device()})
        assert response.status_code == 401, (path, response.text)


async def test_the_device_id_never_reaches_the_logs(auth: AuthHarness) -> None:
    await auth.super_admin()
    handler = RecordingHandler()
    logging.getLogger().addHandler(handler)
    try:
        device_id = device()
        await auth.client.get(f"{auth.prefix}/status", headers={"X-Device-Id": device_id})
    finally:
        logging.getLogger().removeHandler(handler)
    rendered = handler.rendered()
    assert device_id not in rendered
    assert hashlib.sha256(device_id.encode()).hexdigest() not in rendered
