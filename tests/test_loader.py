from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import import_workbook, write_xlsx
from vsa.config import load_settings
from vsa.dictionary_store import load_dictionary
from vsa.loader import (
    build_columns,
    load_stopword_file,
    load_term_dictionary,
    load_term_list,
    object_profiles,
    split_synonyms,
)

ROOT = Path(__file__).resolve().parents[1]


def test_commas_inside_parentheses() -> None:
    assert split_synonyms("aylık ciro (müşteri, kart bazlı), harcama.") == [
        "aylık ciro (müşteri, kart bazlı)",
        "harcama",
    ]


class TestBuildColumns:
    def test_sample_file(self, sample_store_path: Path) -> None:
        d = load_dictionary(sample_store_path)
        keys = [c.key for c in d.columns]
        # whitespace trimmed, duplicate dropped
        assert keys == [
            "EDWDM.CMP.vCardLimitFullness.CardLimitFullnessToday",
            "EDWDM.CMP.vCardLimitFullness.CustomerPartyId",
            "EDWDM.CON.vCreditCardLimit.CardLimitRatio",
        ]
        assert any("Tekrarlanan" in w for w in d.warnings)
        assert d.version.endswith("-4")
        assert len(d.version.split("-")[0]) == 12
        first = d.columns[0]
        assert first.synonyms == (
            "limit doluluk", "kart kullanım oranı", "utilization (kart bazlı)", "fullness",
        )  # fmt: skip
        assert first.dataset_group == "Kart"  # from the object sheet
        assert d.columns[2].has_pii

    def test_correct_spelling_also_accepted(self) -> None:
        rows = [{"DatabaseName": "DB", "SchemaName": "S", "ObjectName": "T",
                 "ColumnName": "C", "ColumnDescription": "d"}]  # fmt: skip
        cols, _ = build_columns(rows)
        assert cols[0].key == "DB.S.T.C"
        assert cols[0].synonyms == () and cols[0].dataset_group is None

    def test_description_is_kept_as_written(self) -> None:
        """Every description counts as verified (ADR-037): brackets are text, not flags."""
        rows = [{"DatabaseName": "DB", "SchemaName": "S", "ObjectName": "T", "ColumnName": "C",
                 "ColumnDescription": " Oran = [(A − B) / B] olarak hesaplanır. "}]  # fmt: skip
        (c,), _ = build_columns(rows)
        assert c.description == "Oran = [(A − B) / B] olarak hesaplanır."

    def test_missing_required_column_raises(self) -> None:
        with pytest.raises(ValueError, match="zorunlu kolon"):
            build_columns([{"SchemaName": "S"}])

    def test_missing_sheet_is_named(self, tmp_path: Path) -> None:
        path = write_xlsx(tmp_path / "d.xlsx", {"Sayfa1": [{"a": 1}]})
        with pytest.raises(ValueError, match="Kolonlar"):
            import_workbook(path, tmp_path / "d.jsonl")


def test_term_dictionary_seed() -> None:
    groups = load_term_dictionary(ROOT / "data" / "terms.jsonl")
    by_term = {g.term: g for g in groups}
    assert "kredi" in by_term["fon kullandırım"].equivalents
    assert by_term["fon kullandırım"].domain == "katılım"
    assert "CIF" in by_term["müşteri numarası"].all_terms
    assert len(groups) >= 45


def test_stopwords_seed() -> None:
    stop = load_stopword_file(ROOT / "data" / "stopwords.jsonl")
    assert {"ve", "icin", "nerede"} <= stop  # folded
    assert len(stop) >= 100


def test_jsonl_lists(tmp_path: Path) -> None:
    terms = tmp_path / "t.jsonl"
    terms.write_text(
        '{"term": " müşteri no ", "equivalents": ["hesap no", " ", 5], "domain": "genel"}\n\n'
        '{"term": "", "equivalents": ["boş"]}\n',
        encoding="utf-8",
    )
    (group,) = load_term_dictionary(terms)
    assert group.term == "müşteri no" and group.equivalents == ("hesap no",)
    assert group.domain == "genel" and group.note == ""
    words = tmp_path / "s.jsonl"
    words.write_text('{"word": "Için", "group": "x"}\n{"group": "boş"}\n', encoding="utf-8")
    assert load_stopword_file(words) == frozenset({"icin"})
    assert load_stopword_file(tmp_path / "yok.jsonl") == frozenset()
    words.write_text('{"word": "ve"}\nve\n', encoding="utf-8")
    with pytest.raises(ValueError, match="s.jsonl satır 2"):
        load_stopword_file(words)


def test_old_list_paths_mean_the_jsonl_files(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        "expansion:\n  term_dictionary: config/term_dictionary.csv\n"
        "  stopwords: config/stopwords_tr.txt\n",
        encoding="utf-8",
    )
    s = load_settings(path)
    assert s.expansion.term_dictionary == "data/terms.jsonl"
    assert s.expansion.stopwords == "data/stopwords.jsonl"


def test_real_dictionary(real_dictionary_path: Path, tmp_path: Path) -> None:
    d = load_dictionary(import_workbook(real_dictionary_path, tmp_path / "d.jsonl"))
    assert d.version.endswith("-11136")
    assert len(d.columns) == 11_136 and not d.warnings  # consolidated: no duplicate rows left
    assert len(d.object_keys) == 390
    with_syn = sum(bool(c.synonyms) for c in d.columns)
    assert with_syn / len(d.columns) > 0.99
    assert all(c.object_name == c.object_name.strip() for c in d.columns)
    assert "EDWDM.CMP.vCardLimitFullness.CardLimitFullnessToday" in d.by_key()


def test_synonyms_and_pii() -> None:
    rows = [
        {"DatabaseName": "EDWDM", "SchemaName": "CUS", "ObjectName": "vCustomer",
         "ColumnName": "CustomerName",
         "ColumnDescription": "Müşteri adı; KVKK kapsamında kişisel veri.",
         "Synonyms": "müşteri adı, unvan (tüzel), name."},
        {"DatabaseName": "EDWDM", "SchemaName": "CUS", "ObjectName": "vCustomer",
         "ColumnName": "Period", "ColumnDescription": "Periyot.", "Synonyms": None},
    ]  # fmt: skip
    cols, _ = build_columns(rows)
    assert cols[0].synonyms == ("müşteri adı", "unvan (tüzel)", "name")
    assert cols[0].description == "Müşteri adı; KVKK kapsamında kişisel veri." and cols[0].has_pii
    assert cols[1].synonyms == () and not cols[1].has_pii


def test_group_comes_from_object_sheet() -> None:
    rows = [
        {"DatabaseName": "EDWDM", "SchemaName": "CMP", "ObjectName": "vCardLimitFullness",
         "ColumnName": "Period", "ColumnDescription": "Periyot."},
        {"DatabaseName": "EDWDM", "SchemaName": "CUS", "ObjectName": "vCustomer",
         "ColumnName": "CustomerPartyId", "ColumnDescription": "Müşteri anahtarı."},
    ]  # fmt: skip
    profiles = object_profiles([{"ObjectKey": "EDWDM.CMP.vCardLimitFullness",
                                 "DatasetGroup": "Kart"}])  # fmt: skip
    groups = {k: p.group for k, p in profiles.items()}
    cols, warnings = build_columns(rows, groups=groups)
    assert [c.dataset_group for c in cols] == ["Kart", None] and not warnings


def test_number_cells_read_as_text(tmp_path: Path) -> None:
    path = write_xlsx(tmp_path / "d.xlsx", {"Kolonlar": [
        {"DatabaseName": "DB", "SchemaName": "S", "ObjectName": "T", "ColumnName": 2024,
         "ColumnDescription": 1.0},
    ]})  # fmt: skip
    (c,) = load_dictionary(import_workbook(path, tmp_path / "d.jsonl")).columns
    assert (c.column, c.description) == ("2024", "1")


def test_term_list_parsing() -> None:
    """ADR-033: one fixed format — column A, row 1 is the header, a term per row below."""
    from vsa.loader import parse_term_sheet

    nan = float("nan")
    rows = [["Terim"], [" kredi  kartı "], [None], [nan], ["Kredi kartı"], ["mevduat"]]
    r = parse_term_sheet(rows)
    assert r.terms == ["kredi kartı", "mevduat"] and r.header == "Terim"
    assert r.notes == [
        "2 boş satır atlandı.",
        "1 tekrar eden terim atlandı (ilk geçtiği satır arandı).",
    ]

    # the first row is always the header, even when it reads like a term — and it is said
    r = parse_term_sheet([["kredi kartı"], ["mevduat"]])
    assert r.terms == ["mevduat"]
    assert r.notes == ["İlk satır (“kredi kartı”) başlık sayıldı ve aranmadı."]
    assert parse_term_sheet([["Terim"], ["x"]], ["Sayfa2"]).notes == [
        "Yalnız ilk sayfa okundu; şu sayfalardaki veriler alınmadı: Sayfa2."]  # fmt: skip


def test_term_list_file(tmp_path: Path) -> None:
    path = write_xlsx(tmp_path / "t.xlsx", {"Liste": [{"Terim": "kart"}, {"Terim": "mevduat"}],
                                            "Boş": []})  # fmt: skip
    r = load_term_list(path)
    assert r.terms == ["kart", "mevduat"] and r.notes == []  # an empty sheet is not reported
    bad = tmp_path / "x.xlsx"
    bad.write_bytes(b"not a workbook")
    with pytest.raises(ValueError, match="Excel"):
        load_term_list(bad)
    huge = write_xlsx(tmp_path / "h.xlsx", {"Liste": [{"Terim": f"t{i}"} for i in range(2500)]})
    with pytest.raises(ValueError, match="çok fazla satır"):
        load_term_list(huge)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "Dosya boş"),
        ([["Terim", "Açıklama"], ["kart", "x"]], "tek sütunlu olmalı; dosyada A, B"),
        ([[None, "Terim"], [None, "kart"]], "A sütununda olmalı; dosyada veri B"),
        ([[None], ["kart"]], "A1 hücresi boş"),
        ([["Terim"], [None]], "altında aranacak terim yok"),
        ([["Terim"], ["x" * 501]], "2. satır çok uzun"),
    ],
)
def test_term_list_rejects_unclear_files(rows: list[list[object]], message: str) -> None:
    from vsa.loader import parse_term_sheet

    with pytest.raises(ValueError, match=message):
        parse_term_sheet(rows)


def test_term_list_limit() -> None:
    from vsa.loader import MAX_TERMS, parse_term_sheet

    with pytest.raises(ValueError, match="en fazla"):
        parse_term_sheet([["Terim"], *([f"t{i}"] for i in range(MAX_TERMS + 1))])
