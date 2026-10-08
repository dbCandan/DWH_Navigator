"""The sealed API key of an integration (data-dictionary 003-llm-connection Requirement 20).

A wrong key, a changed value, another row, another tenant and another address origin all fail the
same way; the same origin with another path still opens.
"""

import base64
import os
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.secret_cipher import SecretUnreadable
from app.domain.llm import LlmOutcome
from app.domain.models.llm_integration import LlmIntegration
from app.services.llm_connections import ConnectionKeys

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-4000-8000-000000000010"
KEY = "sahte-anahtar-123"


def _keys(raw: bytes | None = None) -> ConnectionKeys:
    values: dict[str, Any] = {}
    if raw is not None:
        values["settings_encryption_key"] = SecretStr(base64.b64encode(raw).decode())
    return ConnectionKeys(Settings(_env_file=None, **values))


def _row(public_id: str = "satir-1", endpoint: str = "http://10.0.0.5:8000/v1") -> LlmIntegration:
    return LlmIntegration(public_id=public_id, endpoint=endpoint, chat_model="m")


def test_a_sealed_key_opens_only_in_its_own_context() -> None:
    secret = os.urandom(32)
    keys = _keys(secret)
    row = _row()
    row.api_key_ciphertext = keys.seal(KEY, tenant_public_id=TENANT, row=row)
    assert row.api_key_ciphertext.startswith("v1.") and KEY not in row.api_key_ciphertext
    assert keys.open(row, tenant_public_id=TENANT) == KEY
    row.endpoint = "http://10.0.0.5:8000/openai/v1"  # same origin, another path
    assert keys.open(row, tenant_public_id=TENANT) == KEY

    failures = [
        (_keys(os.urandom(32)), row.public_id, row.endpoint, TENANT),
        (keys, "satir-2", row.endpoint, TENANT),
        (keys, row.public_id, "http://10.0.0.5:8001/v1", TENANT),
        (keys, row.public_id, "https://10.0.0.5:8000/v1", TENANT),
        (keys, row.public_id, row.endpoint, "00000000-0000-4000-8000-000000000099"),
        (_keys(None), row.public_id, row.endpoint, TENANT),
    ]
    for other_keys, public_id, endpoint, tenant in failures:
        moved = _row(public_id, endpoint)
        moved.api_key_ciphertext = row.api_key_ciphertext
        with pytest.raises(SecretUnreadable):
            other_keys.open(moved, tenant_public_id=tenant)
        assert other_keys.connection(moved, tenant_public_id=tenant) is LlmOutcome.KEY_UNREADABLE

    changed = _row()
    changed.api_key_ciphertext = row.api_key_ciphertext[:-2] + (
        "AA" if not row.api_key_ciphertext.endswith("AA") else "BB"
    )
    with pytest.raises(SecretUnreadable):
        keys.open(changed, tenant_public_id=TENANT)


def test_a_row_without_a_key_is_a_keyless_connection() -> None:
    connection = _keys(None).connection(_row(), tenant_public_id=TENANT)
    assert not isinstance(connection, LlmOutcome) and connection.api_key is None
