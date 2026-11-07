"""Dictionary template parsing (dictionary-management Decision 1). The word lists and the
term list have their own readers (vocabulary-management, list-search)."""

from __future__ import annotations

import pytest

from app.domain.analysis import Dictionary
from app.services.analysis.loader import build_columns, object_profiles, split_synonyms
from tests.unit.analysis.workbooks import import_workbook, xlsx_bytes

pytestmark = pytest.mark.unit


def test_commas_inside_parentheses() -> None:
    assert split_synonyms("aylık ciro (müşteri, kart bazlı), harcama.") == [
        "aylık ciro (müşteri, kart bazlı)",
        "harcama",
    ]


class TestBuildColumns:
    def test_sample_file(self, sample_dictionary: Dictionary) -> None:
        d = sample_dictionary
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

    def test_missing_sheet_is_named(self) -> None:
        with pytest.raises(ValueError, match="Kolonlar"):
            import_workbook(xlsx_bytes({"Sayfa1": [{"a": 1}]}))


def test_real_dictionary(real_workbook: bytes) -> None:
    d = import_workbook(real_workbook)
    assert d.version.endswith("-11136")
    assert len(d.columns) == 11_136 and not d.warnings  # consolidated: no duplicate rows left
    assert len(d.object_keys) == 390
    with_syn = sum(bool(c.synonyms) for c in d.columns)
    assert with_syn / len(d.columns) > 0.99
    assert all(c.object_name == c.object_name.strip() for c in d.columns)
    assert "EDWDM.CMP.vCardLimitFullness.CardLimitFullnessToday" in d.by_key()


def test_synonyms() -> None:
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
    assert cols[0].description == "Müşteri adı; KVKK kapsamında kişisel veri."
    assert cols[1].synonyms == ()


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


def test_number_cells_read_as_text() -> None:
    data = xlsx_bytes({"Kolonlar": [
        {"DatabaseName": "DB", "SchemaName": "S", "ObjectName": "T", "ColumnName": 2024,
         "ColumnDescription": 1.0},
    ]})  # fmt: skip
    (c,) = import_workbook(data).columns
    assert (c.column, c.description) == ("2024", "1")
