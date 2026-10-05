from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from vsa.loader import (
    build_columns,
    load_dictionary,
    load_term_dictionary,
    parse_description,
    split_synonyms,
)
from vsa.models import FlagKind

ROOT = Path(__file__).resolve().parents[1]


class TestParseDescription:
    def test_synonyms_extracted(self) -> None:
        body, syn, flags = parse_description(
            "Tekil müşteri numarası (CIF). "
            "Eş anlamlılar/aranabilir terimler: müşteri no, CIF, customer id."
        )
        assert body == "Tekil müşteri numarası (CIF)."
        assert syn == ("müşteri no", "CIF", "customer id")
        assert flags == ()

    @pytest.mark.parametrize("marker", ["Eş anlamlılar:", "aranabilir terimler:"])
    def test_marker_variants(self, marker: str) -> None:
        _, syn, _ = parse_description(f"Açıklama. {marker} a1, b2")
        assert syn == ("a1", "b2")

    def test_commas_inside_parentheses(self) -> None:
        assert split_synonyms("aylık ciro (müşteri, kart bazlı), harcama.") == [
            "aylık ciro (müşteri, kart bazlı)",
            "harcama",
        ]

    def test_model_estimated_flag(self) -> None:
        body, _, flags = parse_description("[MODEL TAHMİNİ — DOĞRULANMALI] Bayrak alanı.")
        assert body == "Bayrak alanı."
        assert [f.kind for f in flags] == [FlagKind.MODEL_ESTIMATED]

    def test_corrected_flag_keeps_note(self) -> None:
        _, _, flags = parse_description(
            "[ORİJİNAL AÇIKLAMA HATALIYDI — DÜZELTİLDİ. Kaynakta 'X' yazıyordu.] Metin."
        )
        assert flags[0].kind is FlagKind.CORRECTED
        assert "Kaynakta 'X'" in flags[0].text

    def test_other_bracket_needs_verification(self) -> None:
        _, _, flags = parse_description("[BU OBJEDE FARKLI ANLAMDA — DOĞRULANMALI] Metin.")
        assert flags[0].kind is FlagKind.NEEDS_VERIFICATION

    def test_mid_text_brackets_are_not_flags(self) -> None:
        body, _, flags = parse_description("Oran = [(A − B) / B] olarak hesaplanır.")
        assert flags == ()
        assert "[(A − B) / B]" in body


class TestBuildColumns:
    def test_sample_file(self, sample_dictionary_path: Path) -> None:
        d = load_dictionary(sample_dictionary_path)
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

    def test_flags_and_quality_sheet(self, sample_dictionary_path: Path) -> None:
        d = load_dictionary(sample_dictionary_path, quality_sheet="Kalite")  # optional sheet
        cols = {c.column: c for c in d.columns}
        assert cols["CustomerPartyId"].has_flag(FlagKind.MODEL_ESTIMATED)
        assert cols["CustomerPartyId"].dataset_group is None
        ratio = cols["CardLimitRatio"]
        assert ratio.has_flag(FlagKind.CORRECTED)
        assert ratio.has_flag(FlagKind.NAMING_MISMATCH)
        assert ratio.has_pii
        assert cols["CardLimitFullnessToday"].has_flag(FlagKind.QUALITY_NOTE)

    def test_missing_quality_sheet_only_warns(self, sample_dictionary_path: Path) -> None:
        d = load_dictionary(sample_dictionary_path, quality_sheet="Yok")
        assert len(d.columns) == 3
        assert any("Kalite sayfası" in w for w in d.warnings)

    def test_correct_spelling_also_accepted(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "DatabaseName": "DB",
                    "SchemaName": "S",
                    "ObjectName": "T",
                    "ColumnName": "C",
                    "ColumnDescription": "d",
                }
            ]
        )
        cols, _ = build_columns(df)
        assert cols[0].key == "DB.S.T.C"

    def test_account_number_meaning_note_dropped(self) -> None:
        """ADR-009: customer no == account no, so this note is noise."""
        base = {"DatabaseName": "DB", "SchemaName": "S", "ObjectName": "T"}
        df = pd.DataFrame(
            [
                {**base, "ColumnName": "AccountNumber",
                 "ColumnDescription": "[BU OBJEDE FARKLI ANLAMDA — DOĞRULANMALI] Hesap no."},
                {**base, "ColumnName": "BranchId",
                 "ColumnDescription": "[BU OBJEDE FARKLI ANLAMDA — DOĞRULANMALI] Şube."},
                {**base, "ColumnName": "DocumentApprovalAccountNumber",
                 "ColumnDescription": "[BU OBJEDE HESAP NUMARASI ANLAMINDA] Hesap no."},
            ]
        )  # fmt: skip
        cols, _ = build_columns(df)
        assert cols[0].flags == ()
        assert cols[1].has_flag(FlagKind.NEEDS_VERIFICATION)
        assert cols[2].flags == ()

    def test_missing_required_column_raises(self) -> None:
        with pytest.raises(ValueError, match="zorunlu kolon"):
            build_columns(pd.DataFrame([{"SchemaName": "S"}]))


def test_term_dictionary_seed() -> None:
    groups = load_term_dictionary(ROOT / "config" / "term_dictionary.csv")
    by_term = {g.term: g for g in groups}
    assert "kredi" in by_term["fon kullandırım"].equivalents
    assert by_term["fon kullandırım"].domain == "katılım"
    assert "CIF" in by_term["müşteri numarası"].all_terms
    assert len(groups) >= 45


def test_real_dictionary(real_dictionary_path: Path) -> None:
    d = load_dictionary(real_dictionary_path)
    assert d.version.endswith("-11136")
    assert len(d.columns) == 11_136 and not d.warnings  # consolidated: no duplicate rows left
    assert len(d.object_keys) == 390
    # every description counts as verified: no leading [...] flags in the column sheet
    assert not any(c.raw_description.startswith("[") for c in d.columns)
    assert not any(c.has_flag(FlagKind.MODEL_ESTIMATED) for c in d.columns)
    with_syn = sum(bool(c.synonyms) for c in d.columns)
    assert with_syn / len(d.columns) > 0.99
    assert all(c.object_name == c.object_name.strip() for c in d.columns)
    assert "EDWDM.CMP.vCardLimitFullness.CardLimitFullnessToday" in d.by_key()


def test_synonyms_column_wins_over_trailing_part() -> None:
    rows = pd.DataFrame({
        "DatabaseName": ["EDWDM", "EDWDM"],
        "SchemaName": ["CUS", "CUS"],
        "ObjectName": ["vCustomer", "vCustomer"],
        "ColumnName": ["CustomerName", "Period"],
        "ColumnDescription": [
            "Müşteri adı; KVKK kapsamında kişisel veri.",
            "Periyot. Eş anlamlılar: dönem, ay",
        ],
        "Synonyms": ["müşteri adı, unvan (tüzel), name.", None],
    })  # fmt: skip
    cols, _ = build_columns(rows)
    assert cols[0].synonyms == ("müşteri adı", "unvan (tüzel)", "name")
    assert cols[0].description == "Müşteri adı; KVKK kapsamında kişisel veri." and cols[0].has_pii
    assert cols[1].synonyms == ("dönem", "ay")  # empty cell: the old trailing form still works


def test_group_comes_from_object_sheet() -> None:
    from vsa.loader import object_groups

    rows = pd.DataFrame({
        "DatabaseName": ["EDWDM", "EDWDM"],
        "SchemaName": ["CMP", "CUS"],
        "ObjectName": ["vCardLimitFullness", "vCustomer"],
        "ColumnName": ["Period", "CustomerPartyId"],
        "ColumnDescription": ["Periyot.", "Müşteri anahtarı."],
    })  # fmt: skip
    objects = pd.DataFrame(
        {"ObjectKey": ["EDWDM.CMP.vCardLimitFullness"], "DatasetGroup": ["Kart"]}
    )
    cols, warnings = build_columns(rows, groups=object_groups(objects))
    assert [c.dataset_group for c in cols] == ["Kart", None] and not warnings


def test_build_catalog() -> None:
    columns = pd.DataFrame({
        "DatabaseName": ["EDWDM", "EDWDM", "EDWDM"],
        "SchemaName": ["CMP", "CMP", "CUS"],
        "ObjectName": ["vCardLimitFullness", "vCardLimitFullness", "vCustomer"],
        "ColumnName": ["CustomerPartyId", "Period", "CustomerPartyId"],
    })  # fmt: skip
    objects = pd.DataFrame({
        "ObjectKey": ["EDWDM.CMP.vCardLimitFullness"],
        "ObjectDescription": ["Kart limit doluluğu."],
        "Grain": ["Kart × Periyot"],
        "KeyColumns": ["CustomerPartyId, Period"],
        "TimeColumns": [None],
        "BusinessDomain": ["Kart ve Harcama"],
        "DatasetGroup": ["Kart"],
    })  # fmt: skip
    from vsa.loader import build_catalog

    (rec,) = build_catalog(objects, columns)
    assert rec["anahtar"] == ["CustomerPartyId", "Period"] and rec["zaman"] == []
    assert rec["kolonlar"] == ["CustomerPartyId", "Period"] and rec["kolon_sayisi"] == 2

    objects.loc[0, "ObjectKey"] = "EDWDM.CMP.vMissing"
    with pytest.raises(ValueError, match="vMissing"):
        build_catalog(objects, columns)


def test_real_catalog(real_dictionary_path: Path, tmp_path: Path) -> None:
    from vsa.loader import write_catalog

    out = tmp_path / "katalog.jsonl"
    assert write_catalog(real_dictionary_path, out) == 390
    assert len(out.read_text(encoding="utf-8").splitlines()) == 390


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
