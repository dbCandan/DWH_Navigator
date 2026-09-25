"""Batch mode helpers (HANDOVER §4.1, §9.4, M5)."""

from __future__ import annotations

from vsa.batch import (
    column_kind,
    entity_column,
    field_entity,
    field_kind,
    field_query,
    is_key_field,
    time_grain,
    wide_siblings,
)
from vsa.features import build_features
from vsa.loader import parse_request_rows
from vsa.models import DictColumn, RequestField
from vsa.scoring.aggregate import ObjectColumns
from vsa.text.normalize import load_stopwords

STOP = load_stopwords([])


def obj(*names: str) -> ObjectColumns:
    feats = tuple(
        build_features(DictColumn(i, "DB", "S", "vT", n, "x", "x"), STOP)
        for i, n in enumerate(names)
    )
    return ObjectColumns("DB.S.vT", feats)


def rf(tr: str, en: str, desc: str = "") -> RequestField:
    return RequestField(1, tr, en, desc)


class TestRequestFile:
    def test_header_with_plural_description(self) -> None:
        rows: list[list[object]] = [
            ["Türkçe Başlık", "İngilizce Başlık", "Açıklamalar"],
            ["Farklı Banka Sayısı", "DistinctBankCount", "Gönderilen farklı banka sayısı"],
            [None, None, None],
        ]
        fields = parse_request_rows(rows)
        assert fields == [
            RequestField(
                1, "Farklı Banka Sayısı", "DistinctBankCount", "Gönderilen farklı banka sayısı"
            )
        ]

    def test_header_below_a_title_and_reordered(self) -> None:
        rows: list[list[object]] = [
            ["Para transferi talebi", None, None],
            ["Açıklama", "English", "Türkçe"],
            ["Ay", "Period", "Dönem"],
        ]
        assert parse_request_rows(rows) == [RequestField(1, "Dönem", "Period", "Ay")]

    def test_no_header_uses_first_three_columns(self) -> None:
        rows: list[list[object]] = [["Dönem", "Period", "YYYYMM"]]
        assert parse_request_rows(rows)[0].en == "Period"


def test_field_query_skips_duplicate_en() -> None:
    assert field_query(rf("CustomerId", "CustomerId", "Müşteri numarası")) == (
        "CustomerId Müşteri numarası"
    )
    assert field_query(rf("Farklı Banka Sayısı", "DistinctBankCount")) == (
        "Farklı Banka Sayısı Distinct Bank Count"
    )


def test_time_grain() -> None:
    assert time_grain([rf("CustomerId", "CustomerId"), rf("Period", "Period")])[0] == "aylık"
    assert time_grain([rf("Gün", "Date")])[0] == "günlük"
    assert time_grain([rf("Tutar", "Amount")]) == ("", None)


def test_key_field() -> None:
    assert is_key_field(rf("CustomerId", "CustomerId"))
    assert is_key_field(rf("Müşteri No", "CIF"))
    assert not is_key_field(rf("Tutar", "Amount"))


def test_field_kind_and_entity() -> None:
    f = rf("Farklı Banka Sayısı", "DistinctBankCount")
    assert field_kind(f) == {"distinct", "count"}
    assert field_entity(f) == "banka"
    assert field_entity(rf("Farklı Alıcı Sayısı", "DistinctTransactionPersonCount")) == "kişi"
    assert field_kind(rf("Transfer Toplamı TL", "TotalTransferAmountTL")) == {"total"}


def test_column_kind() -> None:
    o = obj("FASTIncomingCount", "FASTIncomingAmountTL", "ReceiverBankName")
    kinds = [column_kind(f) for f in o.features]
    assert kinds == [{"count"}, {"total"}, set()]


def test_entity_column_rejects_card_numbers() -> None:
    assert entity_column(obj("BankCardNo"), "banka") is None
    found = entity_column(obj("BankCardNo", "ReceiverBankName"), "banka")
    assert found is not None and found.col.column == "ReceiverBankName"
    person = entity_column(obj("Amount", "ReceiverIdentityNumber"), "kişi")
    assert person is not None and person.col.column == "ReceiverIdentityNumber"


def test_wide_siblings() -> None:
    o = obj(
        "FASTIncomingCount", "KASIncomingCount", "SWIFTIncomingCount", "AccountNumber", "Period"
    )
    lead = o.features[0]
    assert sorted(wide_siblings(o, lead)) == ["KASIncomingCount", "SWIFTIncomingCount"]
    assert wide_siblings(o, o.features[3]) == []  # not a measure
