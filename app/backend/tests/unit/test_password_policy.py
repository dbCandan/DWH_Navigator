"""The password policy matrix (application-foundation/PRDs/001-user-accounts Requirement 3)."""

import secrets
import string

import pytest

from app.domain.password_policy import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    POLICY_MESSAGES,
    PasswordPolicyReason,
    PasswordPolicyViolation,
    check_password_policy,
    common_passwords,
    turkish_fold,
)

pytestmark = pytest.mark.unit

USERNAME = "ad.soyad"
DISPLAY_NAME = "Ayşe Yılmaz"


def _random(length: int) -> str:
    """A throwaway lowercase test-process value of ``length`` characters."""

    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(length))


def _reason(password: str, *, username: str = USERNAME, display_name: str = DISPLAY_NAME) -> str:
    with pytest.raises(PasswordPolicyViolation) as raised:
        check_password_policy(password, username=username, display_name=display_name)
    assert password not in str(raised.value)
    return raised.value.reason.value


def _accepted(password: str, *, username: str = USERNAME, display_name: str = DISPLAY_NAME) -> None:
    check_password_policy(password, username=username, display_name=display_name)


def test_length_bounds_are_15_and_128_unicode_characters() -> None:
    assert (PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH) == (15, 128)
    assert _reason(_random(14)) == "too_short"
    _accepted(_random(15))
    _accepted(_random(128))
    assert _reason(_random(129)) == "too_long"
    # Characters, not bytes: 15 Turkish letters pass although they need 30 bytes.
    _accepted("çğışöüçğışöüçğş")


def test_length_counts_after_nfkc() -> None:
    # The "ﬀ" ligature becomes two letters under NFKC.
    assert _reason("ﬀ" * 7) == "too_short"
    _accepted("ﬀ" * 7 + "x" + "tz")


def test_spaces_and_turkish_letters_are_kept_and_no_composition_is_required() -> None:
    _accepted("bugün deniz kenarında yürüyüş")
    _accepted("   uzun bir cümle seçtim   ")
    _accepted(_random(20))


@pytest.mark.parametrize(
    "password",
    (
        "passwordpassword",
        "PasswordPassword",
        "qwertyuiopasdfgh",
        "1qaz2wsx3edc4rfv",
        "123456789qwerty",
        "a" * 20,
        "abc" * 6,
        "1234" * 5,
        "İİİİİİİİİİİİİİİİ",
    ),
)
def test_common_breached_and_repeated_passwords_are_refused(password: str) -> None:
    assert _reason(password) == "common"


def test_the_offline_list_is_large_folded_and_complete() -> None:
    entries = common_passwords()
    assert len(entries) > 10_000
    assert all(len(entry) >= PASSWORD_MIN_LENGTH for entry in entries)
    assert all(entry == turkish_fold(entry) for entry in entries)
    # The skeleton's original baseline entries stay on the list.
    assert {"passwordpassword", "welcome123456789", "administrator123"} <= entries


@pytest.mark.parametrize(
    ("password", "username", "display_name"),
    (
        ("benim ad.soyad parolam", USERNAME, DISPLAY_NAME),
        ("BENIM AD.SOYAD PAROLAM", USERNAME, DISPLAY_NAME),
        ("yaz tatili ayşe ile gezi", USERNAME, DISPLAY_NAME),
        ("yaz tatili AYSE ile gezi", USERNAME, DISPLAY_NAME),
        ("güzel bir YILMAZ akşamı", USERNAME, DISPLAY_NAME),
        # Turkish dotted and dotless i: "Işık" folds to "isik" from either side.
        ("bu ISIKLI bir sabah olsun", "k.user", "Işık Demir"),
        ("bu ışıklı bir sabah olsun", "k.user", "IŞIK Demir"),
        ("bir İSİM değil isimsiz", "k.user", "İsim Soyisim"),
        ("en sevdiğim dwhnavigator ekranı", "k.user", "Ali Veli"),
        ("NAVIGATOR çok güzel bir araç", "k.user", "Ali Veli"),
    ),
)
def test_account_and_product_names_are_refused_case_insensitively(
    password: str, username: str, display_name: str
) -> None:
    assert _reason(password, username=username, display_name=display_name) == (
        "contains_account_name"
    )


def test_short_display_name_words_do_not_block_a_password() -> None:
    # "Ali" and "Can" have three letters; only words of four or more characters count.
    _accepted("ali ile can bahçede oynuyor", username="k.user", display_name="Ali Can")


def test_reused_has_a_plain_message_and_is_decided_by_the_caller() -> None:
    violation = PasswordPolicyViolation(PasswordPolicyReason.REUSED)
    assert violation.reason.value == "reused"
    assert "şimdiki" in violation.message


def test_every_reason_has_a_turkish_message() -> None:
    assert set(POLICY_MESSAGES) == set(PasswordPolicyReason)
    assert "15" in POLICY_MESSAGES[PasswordPolicyReason.TOO_SHORT]
    assert "uzun bir cümle" in POLICY_MESSAGES[PasswordPolicyReason.TOO_SHORT]


def test_turkish_fold_handles_dotted_and_dotless_i() -> None:
    assert turkish_fold("IŞIK") == "isik"
    assert turkish_fold("İstanbul") == "istanbul"
    assert turkish_fold("ÇĞÖÜŞ") == "cgous"
