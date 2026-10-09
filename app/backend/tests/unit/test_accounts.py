"""Account names, display names and the role hierarchy.

application-foundation/PRDs/001-user-accounts Requirement 1, 2 and 10, Decision 2 and 17.
"""

import pytest

from app.domain.accounts import (
    InvalidDisplayName,
    InvalidUsername,
    account_role,
    application_role_of,
    normalize_username,
    role_satisfies,
    validate_display_name,
    validate_new_username,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("  Ad.Soyad  ", "ad.soyad"),
        ("AD_SOYAD", "ad_soyad"),
        # NFKC turns full-width letters into their ASCII form.
        ("ＡＤＭＩＮ", "admin"),
    ),
)
def test_usernames_are_normalized_with_nfkc_trim_and_lower_case(raw: str, expected: str) -> None:
    assert normalize_username(raw) == expected


@pytest.mark.parametrize("name", ("ali", "ad.soyad", "a_b-c.d", "x" * 64, "  Ad.Soyad "))
def test_new_usernames_use_the_allowed_alphabet(name: str) -> None:
    assert validate_new_username(name) == normalize_username(name)


@pytest.mark.parametrize(
    "name", ("ab", "x" * 65, "ayşe", "ad soyad", "ad@soyad", "", "ışık", "admin!")
)
def test_new_usernames_outside_the_rule_are_refused_without_echo(name: str) -> None:
    with pytest.raises(InvalidUsername) as raised:
        validate_new_username(name)
    assert name == "" or name not in str(raised.value)


def test_display_names_accept_turkish_text_and_trim_spaces() -> None:
    assert validate_display_name("  Ayşe Işık Çağlar  ") == "Ayşe Işık Çağlar"
    assert validate_display_name("x" * 128) == "x" * 128


@pytest.mark.parametrize(
    "name", ("", "   ", "x" * 129, "Ali\x00Veli", "Ali\nVeli", "Ali\u200bVeli")
)
def test_display_names_outside_the_rule_are_refused(name: str) -> None:
    with pytest.raises(InvalidDisplayName):
        validate_display_name(name)


def test_manager_meets_the_user_role_and_super_admin_meets_every_role() -> None:
    assert role_satisfies({"kullanici"}, "kullanici")
    assert not role_satisfies({"kullanici"}, "yonetici")
    assert role_satisfies({"yonetici"}, "kullanici")
    assert role_satisfies({"yonetici"}, "yonetici")
    assert not role_satisfies({"yonetici"}, "super_admin")
    assert role_satisfies({"super_admin"}, "yonetici")
    assert role_satisfies({"super_admin"}, "super_admin")
    assert not role_satisfies(set(), "kullanici")
    assert not role_satisfies({"kullanici"}, "unknown-role")


def test_the_account_role_names_the_super_admin_first() -> None:
    assert application_role_of(("kullanici",)) == "kullanici"
    assert application_role_of(()) is None
    assert account_role(("kullanici", "super_admin")) == "super_admin"
    assert account_role(("yonetici",)) == "yonetici"
    assert account_role(()) is None
