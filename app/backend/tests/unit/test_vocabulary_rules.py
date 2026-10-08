"""The word list checks and their Excel form (vocabulary-management Requirement 2-4, 6, 7).

The checks and messages are the source's ``check_terms`` / ``check_stopwords`` with the new
limits; the workbook is the source's ``words_to_workbook`` / ``words_from_workbook``. The parity
test compares both with the source itself (tests/parity/test_admin_parity.py).
"""

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook

from app.domain.vocabulary import (
    VocabularyList,
    VocabularyRejected,
    VocabularyShapeError,
    check_stopwords,
    check_terms,
    list_digest,
)
from app.infrastructure.excel import reader
from app.infrastructure.excel.writer import workbook_bytes
from app.services.vocabulary_reading import stopword_forms, term_groups
from app.services.vocabulary_workbook import items_from_workbook, items_to_workbook

pytestmark = pytest.mark.unit

SEED = Path(__file__).resolve().parents[4] / "schema" / "alembic" / "seed" / "vocabulary"


def _seed(name: str) -> list[dict[str, Any]]:
    lines = (SEED / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _refused(check: Any, items: object) -> tuple[str, str]:
    with pytest.raises(VocabularyRejected) as refused:
        check(items)
    return refused.value.code, refused.value.message


def test_the_seed_lists_give_the_sources_45_groups_and_124_forms() -> None:
    groups = term_groups(_seed("terms.jsonl"))
    assert len(groups) == 45 and groups[0].term == "fon kullandırım"
    words = _seed("stopwords.jsonl")
    assert len(words) == 106 and len(stopword_forms(words)) == 124
    # The first save folds mi/mı and mu/mü together: 104 rows, the same 124 forms.
    checked = check_stopwords(words)
    assert len(checked) == 104 and stopword_forms(checked) == stopword_forms(words)


def test_term_checks_clean_and_keep_the_order() -> None:
    (row,) = check_terms([{"term": " a ", "equivalents": ["b", "b", " ", "c"]}])
    assert row == {"term": "a", "equivalents": ["b", "c"], "domain": "", "note": ""}
    seed = _seed("terms.jsonl")
    assert check_terms(seed) == seed


@pytest.mark.parametrize(
    ("items", "code", "message"),
    [
        ("değil", "vocabulary_items_invalid", "Liste bekleniyordu"),
        ([1], "vocabulary_items_invalid", "Liste bekleniyordu"),
        (None, "vocabulary_items_invalid", "Liste bekleniyordu"),
        (
            [{"term": "x", "equivalents": ["y"]}] * 5001,
            "vocabulary_too_many_items",
            "En fazla 5000 kayıt",
        ),
        ([{"term": " ", "equivalents": ["y"]}], "vocabulary_term_empty", "Satır 1: terim boş"),
        (
            [{"term": "a", "equivalents": ["b"]}, {"term": "x"}],
            "vocabulary_term_without_equivalents",
            "“x”: en az bir eşdeğer gerekli",
        ),
        (
            [
                {"term": "İŞLEM", "equivalents": ["a"]},
                {"term": "y", "equivalents": ["b"]},
                {"term": "islem", "equivalents": ["c"]},
            ],
            "vocabulary_term_duplicate",
            "“islem” iki kez var (satır 1 ve 3)",
        ),
        (
            [{"term": "t" * 201, "equivalents": ["a"]}],
            "vocabulary_value_too_long",
            "Satır 1: terim en fazla 200 karakter olabilir",
        ),
        (
            [{"term": "t", "equivalents": ["e" * 201]}],
            "vocabulary_value_too_long",
            "“t”: eşdeğer en fazla 200 karakter olabilir",
        ),
        (
            [{"term": "t", "equivalents": ["a"], "domain": "d" * 101}],
            "vocabulary_value_too_long",
            "“t”: alan en fazla 100 karakter olabilir",
        ),
        (
            [{"term": "t", "equivalents": ["a"], "note": "n" * 1001}],
            "vocabulary_value_too_long",
            "“t”: not en fazla 1000 karakter olabilir",
        ),
        (
            [{"term": "t", "equivalents": [f"e{i}" for i in range(101)]}],
            "vocabulary_too_many_equivalents",
            "“t”: en fazla 100 eşdeğer olabilir",
        ),
    ],
)
def test_term_checks_refuse_with_the_sources_messages(
    items: object, code: str, message: str
) -> None:
    assert _refused(check_terms, items) == (code, message)


def test_term_limits_hold_at_their_bounds() -> None:
    item = {
        "term": "t" * 200,
        "equivalents": [f"{i:03d}" + "e" * 197 for i in range(100)],
        "domain": "d" * 100,
        "note": "n" * 1000,
    }
    assert check_terms([item])[0]["note"] == "n" * 1000


@pytest.mark.parametrize(
    ("items", "location"),
    [
        ([{"term": 5, "equivalents": ["a"]}], "items.0.term"),
        ([{"term": "t", "equivalents": "a"}], "items.0.equivalents"),
        ([{"term": "t", "equivalents": ["a", 1]}], "items.0.equivalents"),
        ([{"term": "t", "equivalents": ["a"], "domain": None}], "items.0.domain"),
        ([{"term": "t", "equivalents": ["a"], "note": 3}], "items.0.note"),
        ([{"term": "t", "equivalents": ["a"], "extra": "x"}], "items.0"),
    ],
)
def test_term_fields_have_strict_types(items: object, location: str) -> None:
    with pytest.raises(VocabularyShapeError) as refused:
        check_terms(items)
    assert refused.value.location == location


def test_stopword_checks() -> None:
    assert check_stopwords(
        [{"word": "Ve"}, {"word": "ve"}, {"word": " "}, {"word": "mı", "group": "Soru"}]
    ) == [
        {"word": "Ve", "group": ""},
        {"word": "mı", "group": "Soru"},
    ]
    assert _refused(check_stopwords, [{"word": "iki kelime"}]) == (
        "vocabulary_stopword_not_single_word",
        "“iki kelime”: durak kelime tek kelime olmalı",
    )
    assert _refused(check_stopwords, [{"word": "k" * 101}]) == (
        "vocabulary_value_too_long",
        f"“{'k' * 101}”: durak kelime en fazla 100 karakter olabilir",
    )
    assert _refused(check_stopwords, [{"word": "ve", "group": "g" * 201}]) == (
        "vocabulary_value_too_long",
        "“ve”: grup adı en fazla 200 karakter olabilir",
    )
    with pytest.raises(VocabularyShapeError):
        check_stopwords([{"word": 1}])


def test_the_list_digest_follows_order_and_content() -> None:
    a = [{"word": "ve", "group": ""}, {"word": "ile", "group": ""}]
    assert list_digest(a) != list_digest(list(reversed(a)))
    assert list_digest(a) == list_digest([dict(reversed(list(i.items()))) for i in a])
    assert len(list_digest(a)) == 64


def _workbook(title: str, rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    return workbook_bytes(book)


def test_a_list_goes_to_excel_and_comes_back() -> None:
    terms = check_terms(_seed("terms.jsonl"))
    data = items_to_workbook(VocabularyList.TERMS, terms)
    book = load_workbook(BytesIO(data))
    sheet = book["Terimler"]
    assert [c.value for c in sheet[1]] == ["Terim", "Eşdeğerler", "Alan", "Not"]
    assert all(c.font.bold for c in sheet[1])
    assert sheet.freeze_panes == "A2"
    assert [sheet.column_dimensions[k].width for k in "ABCD"] == [28, 70, 16, 50]
    assert check_terms(items_from_workbook(VocabularyList.TERMS, data)) == terms
    words = check_stopwords(_seed("stopwords.jsonl"))
    back = items_from_workbook(
        VocabularyList.STOPWORDS, items_to_workbook(VocabularyList.STOPWORDS, words)
    )
    assert check_stopwords(back) == words


def test_an_edited_workbook_is_read_like_the_source() -> None:
    data = _workbook(
        "Başka",
        [
            [" TERİM ", "Eş Değerler", "açıklama", "ignored"],
            ["zırhlı araç", "panzer; tank, =zırh|kale\nkule", "Not metni", "x"],
            [None, None, None, None],
            [5.0, 12, None, None],
        ],
    )
    items = items_from_workbook(VocabularyList.TERMS, data)
    assert items == [
        {"term": "zırhlı araç", "equivalents": ["panzer", "tank", "=zırh", "kale", "kule"],
         "note": "Not metni"},
        {"term": "5", "equivalents": ["12"], "note": ""},
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("data", "code", "message"),
    [
        (b"not excel", "vocabulary_workbook_unreadable", "Dosya Excel (.xlsx) olarak okunamadı."),
        (
            _workbook("DurakKelimeler", [["Grup"], ["g"]]),
            "vocabulary_workbook_column_missing",
            (
                "“Kelime” sütunu bulunamadı; dışa aktarılan dosyanın başlıklarını koruyun "
                "(Kelime, Grup)."
            ),
        ),
        (
            _workbook("DurakKelimeler", [["Kelime", "Grup"], [None, None]]),
            "vocabulary_workbook_empty",
            "“DurakKelimeler” sayfasında kayıt yok.",
        ),
        (
            _workbook("DurakKelimeler", [["Kelime"], *[[f"k{i}"] for i in range(5001)]]),
            "vocabulary_workbook_too_many_rows",
            "Dosyada çok fazla satır var (en fazla 5000).",
        ),
    ],
)
def test_workbook_refusals(data: bytes, code: str, message: str) -> None:
    with pytest.raises(VocabularyRejected) as refused:
        items_from_workbook(VocabularyList.STOPWORDS, data)
    assert (refused.value.code, refused.value.message) == (code, message)


def test_the_named_sheet_is_read_before_the_first(monkeypatch: pytest.MonkeyPatch) -> None:
    book = Workbook()
    book.active.title = "İlk"
    book.active.append(["Kelime"])
    book.active.append(["ilk"])
    named = book.create_sheet("DurakKelimeler")
    named.append(["Kelime"])
    named.append(["adlı"])
    data = workbook_bytes(book)
    assert items_from_workbook(VocabularyList.STOPWORDS, data) == [{"word": "adlı"}]
    monkeypatch.setattr(reader, "MAX_UNPACKED_BYTES", 100)
    with pytest.raises(VocabularyRejected) as refused:
        items_from_workbook(VocabularyList.STOPWORDS, data)
    assert refused.value.code == "vocabulary_workbook_unreadable"
    assert refused.value.message == "Dosya açıldığında çok büyük (en fazla 100 MB)."
