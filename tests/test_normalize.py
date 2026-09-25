from __future__ import annotations

import re
from pathlib import Path

import pytest

from vsa.text.normalize import (
    ascii_fold,
    fold,
    load_stopwords,
    normalize_phrase,
    split_camel,
    stem,
    tokenize,
    tr_lower,
    tr_upper,
)

STOP = load_stopwords(["ve", "bilgisi", "verisi", "için", "tablo", "# yorum", ""])


class TestTurkishCase:
    def test_dotted_capital_i(self) -> None:
        assert tr_lower("İHTİYAÇ") == "ihtiyaç"

    def test_dotless_capital_i(self) -> None:
        assert tr_lower("KIRILIM") == "kırılım"

    def test_python_lower_is_wrong(self) -> None:
        # Documents why the module exists: plain lower() yields a combining dot.
        assert "İ".lower() != "i"
        assert tr_lower("İ") == "i"

    def test_all_turkish_capitals(self) -> None:
        assert tr_lower("IİŞĞÜÖÇ") == "ıişğüöç"

    def test_upper(self) -> None:
        assert tr_upper("ihtiyaç ılık") == "İHTİYAÇ ILIK"


class TestAsciiFold:
    def test_fold_chars(self) -> None:
        assert ascii_fold("ışğüöçâîû") == "isguocaiu"

    def test_fold_full(self) -> None:
        assert fold("Müşteri İhtiyaç Kâr") == "musteri ihtiyac kar"

    def test_user_typed_ascii_matches(self) -> None:
        assert fold("ihtiyac kredisi") == fold("İhtiyaç Kredisi")


class TestCamelCase:
    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("CardLimitFullnessToday", ["Card", "Limit", "Fullness", "Today"]),
            ("IFRSStage", ["IFRS", "Stage"]),
            ("TOTALOUTSTANDINGBALANCE", ["TOTALOUTSTANDINGBALANCE"]),
            ("KKB_DATE", ["KKB", "DATE"]),
            ("CustomerPartyId", ["Customer", "Party", "Id"]),
            ("Avg30d", ["Avg", "30", "d"]),
            ("vPRCArrayAllotment", ["v", "PRC", "Array", "Allotment"]),
            ("SWIFTCountL12M", ["SWIFT", "Count", "L", "12", "M"]),
            ("müşteri", ["müşteri"]),
        ],
    )
    def test_split(self, word: str, expected: list[str]) -> None:
        assert split_camel(word) == expected


class TestStem:
    @pytest.mark.parametrize(
        ("variants", "root"),
        [
            (["transferi", "transferler", "transferlerin", "transferlerinin"], "transfer"),
            (["kredisi", "kredileri", "kredilerin"], None),
            (["musteri", "musterinin", "musterilerin", "musteriler"], None),
            (["kartlar", "kartlarin", "kart"], "kart"),
        ],
    )
    def test_variants_share_stem(self, variants: list[str], root: str | None) -> None:
        stems = {stem(v) for v in variants}
        assert len(stems) == 1, stems
        if root is not None:
            assert stems == {root}

    def test_min_root_length(self) -> None:
        assert stem("data") == "data"
        assert stem("risk") == "risk"

    def test_digits_untouched(self) -> None:
        assert stem("2024") == "2024"


class TestTokenize:
    def test_stopwords_token_level(self) -> None:
        # "bilgisi" is a stopword but "risk" must survive (HANDOVER §6.5).
        assert tokenize("risk bilgisi", stopwords=STOP) == ["risk"]

    def test_camel_with_compound(self) -> None:
        toks = tokenize("CardLimitFullnessToday", do_stem=False)
        assert toks == ["card", "limit", "fullness", "today", "cardlimitfullnesstoday"]

    def test_exact_identifier_query_matches_index(self) -> None:
        q = tokenize("CreditCardLimitRate")
        doc = tokenize("CreditCardLimitRate")
        assert set(q) == set(doc)
        assert "creditcardlimitrate" in {t for t in q}

    def test_ascii_and_turkish_query_equal(self) -> None:
        assert tokenize("ihtiyac kredisi", stopwords=STOP) == tokenize(
            "İHTİYAÇ KREDİSİ", stopwords=STOP
        )

    def test_punctuation_and_single_letters_dropped(self) -> None:
        assert tokenize("a, (b) — kart.", do_stem=False) == ["kart"]

    def test_underscore_splits(self) -> None:
        assert tokenize("KKB_DATE", do_stem=False) == ["kkb", "date", "kkbdate"]


class TestPhrase:
    def test_phrase_containment(self) -> None:
        desc = normalize_phrase("Kredi kartı limit doluluk oranını gösterir.")
        assert normalize_phrase("limit doluluk oranı") in desc

    def test_stopwords_file(self) -> None:
        assert "icin" in STOP  # folded
        assert "# yorum" not in STOP


def test_no_direct_lower_calls_outside_normalize() -> None:
    """HANDOVER §6.1: no module may call .lower()/.upper()/.casefold() directly."""
    src = Path(__file__).resolve().parents[1] / "src" / "vsa"
    pattern = re.compile(r"\.(lower|upper|casefold)\(\)")
    offenders = [
        f"{p.relative_to(src)}:{i}"
        for p in src.rglob("*.py")
        if p.name != "normalize.py"
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
