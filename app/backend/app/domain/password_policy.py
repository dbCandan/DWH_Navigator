"""The password policy of every password a person chooses (rules/58, NIST SP 800-63-4 direction).

application-foundation/PRDs/001-user-accounts Requirement 3 and Decision 19. After NFKC the
password counts Unicode characters: 15 at least, 128 at most; spaces and Turkish letters stay as
entered and no character class is required. A password is refused when it is on the offline list
of common and breached passwords or repeats one short unit, or when it contains the username, a
display-name word of four or more characters or the product name. The comparison folds case with
Turkish rules (``I`` to ``ı``, ``İ`` to ``i``) and Turkish letters to ASCII, so ``IŞIK`` and
``ışık`` match ``isik``. Whether the password equals the account's current or one-time password is
checked by the caller against the stored hash (``reused``).
"""

import re
import unicodedata
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 128
DISPLAY_NAME_WORD_MIN_LENGTH = 4
PRODUCT_NAMES = ("dwhnavigator", "navigator")
# Offline list of common and breached passwords of at least 15 characters, stored folded, sorted and
# without duplicates. Its sources are recorded in specs/application-foundation/PRDs/
# 001-user-accounts/plan.md and dependency-admission.json.
COMMON_PASSWORDS_FILE = Path(__file__).with_name("common_passwords.txt")

_TURKISH_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_ASCII_FOLD = str.maketrans(
    {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)
_WORD_RE = re.compile(r"[^\W_]+")


class PasswordPolicyReason(StrEnum):
    """Why a chosen password was refused; the ``reason`` of the 422 ``password_policy`` answer."""

    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    COMMON = "common"
    CONTAINS_ACCOUNT_NAME = "contains_account_name"
    REUSED = "reused"


# The person-facing explanation of each reason (Turkish, plain language).
POLICY_MESSAGES: dict[PasswordPolicyReason, str] = {
    PasswordPolicyReason.TOO_SHORT: (
        f"Parola en az {PASSWORD_MIN_LENGTH} karakter olmalı; uzun bir cümle seçebilirsiniz."
    ),
    PasswordPolicyReason.TOO_LONG: f"Parola en çok {PASSWORD_MAX_LENGTH} karakter olabilir.",
    PasswordPolicyReason.COMMON: (
        "Bu parola çok yaygın ya da kolay tahmin edilir; başka bir parola seçin."
    ),
    PasswordPolicyReason.CONTAINS_ACCOUNT_NAME: (
        "Parola kullanıcı adınızı, adınızı ya da uygulamanın adını içeremez."
    ),
    PasswordPolicyReason.REUSED: "Yeni parola şimdiki parolanızla aynı olamaz.",
}


class PasswordPolicyViolation(ValueError):
    """The password breaks the policy; the message names the rule, never the password."""

    def __init__(self, reason: PasswordPolicyReason) -> None:
        super().__init__(reason.value)
        self.reason = reason

    @property
    def message(self) -> str:
        return POLICY_MESSAGES[self.reason]


def normalize_password(raw: str) -> str:
    """NFKC without trimming (Requirement 1 and 3)."""

    return unicodedata.normalize("NFKC", raw)


def turkish_fold(text: str) -> str:
    """Lower-case with Turkish rules, then fold Turkish letters to ASCII."""

    return text.translate(_TURKISH_LOWER).lower().translate(_ASCII_FOLD)


@lru_cache(maxsize=1)
def common_passwords() -> frozenset[str]:
    lines = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(turkish_fold(line) for line in lines if line)


def _repeats_a_short_unit(value: str) -> bool:
    """Detect passwords such as ``aaaa...`` or ``abcabc...`` built from one short repeated unit."""

    return any(
        len(value) % size == 0 and value == value[:size] * (len(value) // size)
        for size in range(1, 5)
    )


def _account_words(username: str, display_name: str) -> list[str]:
    words = [turkish_fold(username)] if username else []
    words += [
        word
        for word in _WORD_RE.findall(turkish_fold(display_name))
        if len(word) >= DISPLAY_NAME_WORD_MIN_LENGTH
    ]
    words += list(PRODUCT_NAMES)
    return words


def check_password_policy(password: str, *, username: str, display_name: str) -> None:
    """Raise PasswordPolicyViolation for the first rule the password breaks.

    ``reused`` is not decided here: it needs the stored hash of the account's current password.
    """

    normalized = normalize_password(password)
    if len(normalized) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyViolation(PasswordPolicyReason.TOO_SHORT)
    if len(normalized) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyViolation(PasswordPolicyReason.TOO_LONG)
    folded = turkish_fold(normalized)
    if folded in common_passwords() or _repeats_a_short_unit(folded):
        raise PasswordPolicyViolation(PasswordPolicyReason.COMMON)
    if any(word and word in folded for word in _account_words(username, display_name)):
        raise PasswordPolicyViolation(PasswordPolicyReason.CONTAINS_ACCOUNT_NAME)
