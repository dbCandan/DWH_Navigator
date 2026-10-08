"""Password hashing, one-time passwords, refresh tokens and signed JWT access-token primitives."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.domain.password_policy import normalize_password

_password_hash = PasswordHash.recommended()

# application-foundation 001 Requirement 2: 20 characters of lower-case letters and digits without
# the easily confused 0, o, 1, l and i. 31 symbols give about 99 bits of randomness.
ONE_TIME_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
ONE_TIME_PASSWORD_LENGTH = 20
REFRESH_TOKEN_BYTES = 32
_LOGIN_NAME_DIGEST_CONTEXT = b"dwhnavigator:login-name-digest:v1\0"


class TokenClaims(BaseModel):
    """Claims trusted by request middleware after signature and audience validation."""

    sub: UUID
    username: str
    tenant_id: UUID
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    is_super_admin: bool = False
    exp: int
    iat: int
    iss: str
    aud: str


def hash_password(password: str) -> str:
    """Argon2 hash of the NFKC form (never trimmed); the caller applies the policy beforehand."""

    return _password_hash.hash(normalize_password(password))


@lru_cache(maxsize=1)
def _unknown_account_hash() -> str:
    return _password_hash.hash(secrets.token_urlsafe(32))


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password; a missing account still spends one hash verification.

    Equal work keeps login response time from revealing whether a username exists.
    """

    try:
        verified = _password_hash.verify(
            normalize_password(password), password_hash or _unknown_account_hash()
        )
    except (ValueError, TypeError):
        return False
    return verified and password_hash is not None


def new_one_time_password() -> str:
    """A CSPRNG one-time password of the Requirement 2 alphabet and length."""

    return "".join(
        secrets.choice(ONE_TIME_PASSWORD_ALPHABET) for _ in range(ONE_TIME_PASSWORD_LENGTH)
    )


def new_refresh_token() -> str:
    """Return a CSPRNG refresh token of 256 bits; only its digest is ever stored."""

    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def refresh_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def login_name_digest(normalized_name: str) -> str:
    """Keyed digest that lets logs correlate failed attempts without the username.

    The key is derived from the deployment's JWT signing key, so the digest is stable inside one
    deployment and cannot be reversed by hashing a guessed name without that secret.
    """

    key_material = get_settings().jwt_private_key.get_secret_value().encode("utf-8")
    key = hashlib.sha256(_LOGIN_NAME_DIGEST_CONTEXT + key_material).digest()
    return hmac.new(key, normalized_name.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def create_access_token(
    *,
    subject: UUID,
    username: str,
    tenant_id: UUID,
    roles: list[str],
    permissions: list[str],
    is_super_admin: bool,
) -> str:
    """Create a short-lived access token."""

    settings = get_settings()
    now = datetime.now(UTC)
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "username": username,
        "tenant_id": str(tenant_id),
        "roles": sorted(set(roles)),
        "permissions": sorted(set(permissions)),
        "is_super_admin": is_super_admin,
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenClaims:
    """Verify a token completely before exposing claims to authorization code."""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_verification_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        return TokenClaims.model_validate(payload)
    except (InvalidTokenError, ValidationError) as exc:
        raise InvalidTokenError("invalid access token") from exc
