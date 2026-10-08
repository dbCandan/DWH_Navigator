"""Local account names, display names and application roles.

application-foundation/PRDs/001-user-accounts Requirement 1, 2 and 10, Decision 2 and 17. A
username is normalized with NFKC, trimmed and lower-cased; a new account name uses only ``a-z``,
``0-9``, ``.``, ``_`` and ``-`` and has 3-64 characters, so lower-casing never meets the Turkish
dotted and dotless i. A display name is free Turkish text without control characters.
"""

import re
import unicodedata
from collections.abc import Iterable

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 64
DISPLAY_NAME_MAX_LENGTH = 128
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")

SUPER_ADMIN_ROLE = "super_admin"
ROLE_USER = "kullanici"
ROLE_MANAGER = "yonetici"
# Decision 2: every account except the super admin holds exactly one of these roles; the manager
# can do everything the user can, so a role satisfies every requirement at or below its rank.
APPLICATION_ROLES = (ROLE_USER, ROLE_MANAGER)
_ROLE_RANK = {ROLE_USER: 1, ROLE_MANAGER: 2}

SUPER_ADMIN_DISPLAY_NAME = "Süper yönetici"


class InvalidUsername(ValueError):
    """The name cannot belong to a local account; the message never repeats the name."""


class InvalidDisplayName(ValueError):
    """The display name is empty, too long or holds a control character."""


def normalize_username(raw: str) -> str:
    """NFKC, surrounding whitespace removed, lower-cased (Requirement 1)."""

    return unicodedata.normalize("NFKC", raw).strip().lower()


def validate_new_username(raw: str) -> str:
    """The normalized name of a new account, or InvalidUsername (Decision 17)."""

    name = normalize_username(raw)
    if _USERNAME_RE.fullmatch(name) is None:
        raise InvalidUsername(
            f"username must have {USERNAME_MIN_LENGTH}-{USERNAME_MAX_LENGTH} characters of "
            "a-z, 0-9, '.', '_' and '-'"
        )
    return name


def validate_display_name(raw: str) -> str:
    """The display name without surrounding whitespace; 1-128 characters, no control character."""

    name = raw.strip()
    if not 1 <= len(name) <= DISPLAY_NAME_MAX_LENGTH:
        raise InvalidDisplayName(f"display name must have 1-{DISPLAY_NAME_MAX_LENGTH} characters")
    if any(unicodedata.category(character).startswith("C") for character in name):
        raise InvalidDisplayName("display name must not contain control characters")
    return name


def application_role_of(role_codes: Iterable[str]) -> str | None:
    """The single application role among assigned role codes, if any."""

    held = set(role_codes)
    granted = [code for code in APPLICATION_ROLES if code in held]
    return granted[-1] if granted else None


def account_role(role_codes: Iterable[str]) -> str | None:
    """The role an account shows: ``super_admin`` for the super admin, else its application role."""

    held = set(role_codes)
    if SUPER_ADMIN_ROLE in held:
        return SUPER_ADMIN_ROLE
    return application_role_of(held)


def role_satisfies(role_codes: Iterable[str], required: str) -> bool:
    """True when the held roles meet ``required``; the super admin meets every role."""

    held = set(role_codes)
    if SUPER_ADMIN_ROLE in held:
        return True
    if required == SUPER_ADMIN_ROLE:
        return False
    needed = _ROLE_RANK.get(required)
    if needed is None:
        return False
    return any(_ROLE_RANK.get(code, 0) >= needed for code in held)
