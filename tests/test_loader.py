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
        cols = {c.column: c for c in load_dictionary(sample_dictionary_path).columns}
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
    assert d.version.endswith("-11158")
    assert 11_100 <= len(d.columns) <= 11_158
    assert len(d.object_keys) >= 389
    estimated = sum(c.has_flag(FlagKind.MODEL_ESTIMATED) for c in d.columns)
    assert 235 <= estimated <= 240
    with_syn = sum(bool(c.synonyms) for c in d.columns)
    assert with_syn / len(d.columns) > 0.99
    assert all(c.object_name == c.object_name.strip() for c in d.columns)
    assert "EDWDM.CMP.vCardLimitFullness.CardLimitFullnessToday" in d.by_key()
