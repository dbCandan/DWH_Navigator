"""The organization root CA of the internal model server, added to the backend release image.

data-dictionary/PRDs/003-llm-connection (Dağıtım etkisi, Task 9); nonprod names the file in
DWHNAVIGATOR_LLM_CA_BUNDLE (application-foundation/PRDs/002-kubernetes-delivery Requirement 8).
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography import x509

from app.core.config import Settings

pytestmark = pytest.mark.unit

CERTIFICATE = Path(__file__).resolve().parents[2] / "certs" / "corporate-inference-root.crt"
# SHA-256 of the reviewed public certificate; the same file DWH Code Review ships for the endpoint.
REVIEWED_SHA256 = "b71be69ffcb25e13684497aa3a5788c17d688a08e44f9bdc99ad1cc480677fc2"


def test_the_trust_store_addition_is_the_reviewed_public_root_certificate() -> None:
    content = CERTIFICATE.read_bytes()
    assert hashlib.sha256(content).hexdigest() == REVIEWED_SHA256
    assert b"PRIVATE KEY" not in content
    (certificate,) = x509.load_pem_x509_certificates(content)
    assert certificate.issuer == certificate.subject
    assert certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert certificate.not_valid_after_utc > datetime(2037, 1, 1, tzinfo=UTC)


def test_the_model_trust_store_setting_accepts_the_certificate() -> None:
    assert Settings.validate_llm_ca_bundle(str(CERTIFICATE)) == str(CERTIFICATE)
