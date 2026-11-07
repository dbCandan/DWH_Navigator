"""The curation rules: what the hand-made dictionary was cleaned with, and the slips found on the way."""

from __future__ import annotations

import pytest

from app.services.dictionary_curation import text_rules as rules
from app.services.dictionary_curation.decisions import Decisions, load, parse
from app.services.dictionary_curation.normalize import (
    KIND_COLUMN,
    KIND_TABLE,
    normalize_tables,
    object_code,
)
from app.services.dictionary_curation.object_rules import align_object, date_key, present_columns
from app.services.dictionary_sync_merge import ORIGIN_EDITED, ORIGIN_MODEL, MergedColumn, MergedTable

# --------------------------------------------------------------------------- doubt


def test_doubting_sentence_goes_and_plain_one_stays() -> None:
    text, removed = rules.remove_doubt(
        "Müşterinin şube kodudur. Değerin anlamı iş birimi ile doğrulanmalıdır."
    )
    assert text == "Müşterinin şube kodudur."
    assert removed == ["Değerin anlamı iş birimi ile doğrulanmalıdır."]


def test_a_doubting_clause_goes_and_the_plain_clause_of_the_sentence_stays() -> None:
    text, _ = rules.remove_doubt("Kayıt tarihidir; kapsamı iş birimi ile doğrulanmalıdır.")
    assert text == "Kayıt tarihidir."


def test_a_text_of_doubt_only_keeps_its_claim() -> None:
    text, _ = rules.remove_doubt("Kartın EMV bayrağı olması beklenmektedir.")
    assert text == "Kartın EMV bayrağı."


def test_model_tag_goes() -> None:
    text, removed = rules.remove_doubt("[MODEL TAHMİNİ - DOĞRULANMALI] Şube adıdır.")
    assert text == "Şube adıdır."
    assert removed[0].startswith("[MODEL TAHMİNİ")


def test_a_bracket_with_a_semicolon_is_not_split_into_a_fragment() -> None:
    """Regression: '(…; ör. Bireysel, KOBİ)' left 'ör. Bireysel, KOBİ).' as the description."""

    text, _ = rules.clean_description(
        "Müşterinin sınıfıdır (kod ya da ad, objeye göre değişebilir; ör. Bireysel, KOBİ). "
        "Finansman teklifi sahibi müşterinin sınıfıdır."
    )
    assert not text.lower().startswith("ör.")
    assert text.startswith("Finansman teklifi") or text.startswith("Müşterinin")


def test_abbreviation_is_not_a_sentence_end() -> None:
    assert rules.sentences("Kalem kodudur (ör. 1.9). İkinci cümle.") == [
        "Kalem kodudur (ör. 1.9).",
        "İkinci cümle.",
    ]


# --------------------------------------------------------------------------- hedges


@pytest.mark.parametrize(
    "sentence",
    [
        "Bu tutarın altındaki işlemlerde SMS bildirimi tetiklenmeyebilir.",
        "Havale dışındaki ödemelerde kullanılmayabilir.",
        "Değer boş olabilir.",
    ],
)
def test_a_hedging_sentence_goes(sentence: str) -> None:
    text, removed = rules.remove_hedges(f"Kartın limit tutarıdır. {sentence}")
    assert text == "Kartın limit tutarıdır."
    assert removed


def test_genellikle_leaves_and_the_statement_stays() -> None:
    assert rules.remove_hedges("Tutar genellikle ay sonu bakiyesidir.")[0] == "Tutar ay sonu bakiyesidir."


def test_okunabilir_is_not_a_hedge() -> None:
    text = "Temlik türünün okunabilir adıdır."
    assert rules.remove_hedges(text) == (text, [])


def test_an_example_the_sources_do_not_hold_goes_and_one_they_hold_stays() -> None:
    assert rules.remove_hedges("Döviz kodudur (ör. TRY, USD).")[0] == "Döviz kodudur."
    kept = rules.remove_hedges("Döviz kodudur (ör. TRY, USD).", sources="... 'TRY' ...")[0]
    assert kept == "Döviz kodudur (ör. TRY, USD)."


def test_usage_boilerplate_goes() -> None:
    text, _ = rules.remove_hedges("Şube kodudur. Şube bazlı analizlerde temel kırılım olarak kullanılır.")
    assert text == "Şube kodudur."


# --------------------------------------------------------------------------- wording


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Faiz tutarıdır.", "Kar payı tutarıdır."),
        ("Kredinin faiz oranıdır.", "Fon kullandırımının kar payı oranıdır."),
        ("Mevduat hesabının bakiyesidir.", "Katılma hesabının bakiyesidir."),
        ("Leasing fon ödemesinin tarihidir.", "İcare fon ödemesinin tarihidir."),
        ("Kredi kartı limitidir.", "Kredi kartı limitidir."),
        ("Faizsiz finansman tutarıdır.", "Faizsiz finansman tutarıdır."),
        ("Kod 'Bireysel Krediler' yazar.", "Kod 'Bireysel Krediler' yazar."),
    ],
)
def test_participation_wording(before: str, after: str) -> None:
    assert rules.participation_wording(before) == after


def test_capital_keeps_names_like_ios() -> None:
    assert rules.capital("icare projesidir.") == "İcare projesidir."
    assert rules.capital("iOS sürümüdür.") == "iOS sürümüdür."


def test_terms_sentence_leaves_the_description() -> None:
    text, _ = rules.clean_description("Şube adıdır. Eş anlamlılar/aranabilir terimler: şube, branch.")
    assert text == "Şube adıdır."


# --------------------------------------------------------------------------- search terms


def test_a_hedged_search_term_goes() -> None:
    """Regression: 'TCKN (bazı durumlarda)' stood among the terms of ten TaxNumber columns."""

    assert rules.clean_synonyms("VKN, vergi numarası, TCKN (bazı durumlarda), tax ID") == (
        "VKN, vergi numarası, tax ID"
    )


def test_only_an_exact_repeat_goes() -> None:
    assert rules.clean_synonyms("işlem etiketi, Transaction Label, transaction label, işlem etiketi") == (
        "işlem etiketi, Transaction Label, transaction label"
    )


def test_the_general_banking_word_joins_once() -> None:
    synonyms = rules.clean_synonyms("katılma hesabı bakiyesi", "Katılma hesabının bakiyesidir.")
    assert synonyms == "katılma hesabı bakiyesi, mevduat"
    assert rules.clean_synonyms(synonyms, "Katılma hesabının bakiyesidir.") == synonyms


def test_no_terms_stay_no_terms() -> None:
    assert rules.clean_synonyms("", "Kar payı tutarıdır.") == ""


# --------------------------------------------------------------------------- summary


def test_a_value_list_the_code_does_not_hold_goes() -> None:
    assert rules.clean_summary("Müşteri sınıfı · Bireysel/KOBİ/Ticari/Kurumsal") == "Müşteri sınıfı"
    assert rules.clean_summary("Döviz cinsi kodu (TRY, USD, EUR)") == "Döviz cinsi kodu"


def test_a_value_list_the_code_writes_stays() -> None:
    """Regression: lists of quoted values in the object's code were cut too."""

    support = rules.code_literals(["CASE WHEN x=1 THEN 'Yatırım Fonu' WHEN x=2 THEN 'Hisse Senedi' ELSE 'Sukuk' END"])
    summary = "Yatırım aracı tipi (Yatırım Fonu, Hisse Senedi, Sukuk)"
    assert rules.clean_summary(summary, support) == summary


def test_summary_drops_doubt_and_examples_and_stays_short() -> None:
    assert rules.clean_summary("Kalem kodu (ör. 1.9) · olası değerler doğrulanmalı") == "Kalem kodu"
    long = "Müşterinin son on iki aydaki ortalama katılma hesabı bakiyesi toplamının Türk lirası karşılığı"
    clipped = rules.clean_summary(long, limit=70)
    assert len(clipped) <= 70 and long.startswith(clipped)


@pytest.mark.parametrize(
    "text",
    [
        "Müşterinin sınıfıdır (kod ya da ad, objeye göre değişebilir; ör. Bireysel, KOBİ). Teklif sahibinin sınıfıdır.",
        "[MODEL TAHMİNİ] Kredinin faiz oranıdır; iş birimi ile doğrulanmalıdır. Leasing projesidir.",
        "Tutar genellikle ay sonu bakiyesidir (ör. 100, 200). Eş anlamlılar: tutar.",
    ],
)
def test_the_description_rules_are_idempotent(text: str) -> None:
    once, _ = rules.clean_description(text)
    assert rules.clean_description(once) == (once, [])


# --------------------------------------------------------------------------- objects


def test_key_columns_name_columns_the_object_has_in_its_spelling() -> None:
    assert present_columns("customerid, Missing, CustomerId, Period", ["CustomerId", "Period"]) == [
        "CustomerId",
        "Period",
    ]


@pytest.mark.parametrize(
    ("grain", "expected"),
    [
        ("Teminat × Veri tarihi", ["CollateralId", "DataDate"]),
        ("Müşteri × Periyot (ay)", ["CollateralId", "Period"]),
        ("Teminat", ["CollateralId"]),
    ],
)
def test_a_grain_cut_by_a_date_has_the_date_in_its_keys(grain: str, expected: list[str]) -> None:
    assert date_key(grain, ["CollateralId"], ["DataDate", "Period"]) == expected


def test_align_object_reports_only_what_changes() -> None:
    decisions = Decisions(domain_aliases={"Kârlılık": "Karlılık ve Fiyatlama"})
    record = {"KeyColumns": "AccountNumber, SectorName", "TimeColumns": "Datadate", "Grain": "Hesap × Veri tarihi",
              "BusinessDomain": "Kârlılık"}
    changed = align_object(record, ["AccountNumber", "DataDate"], decisions)
    assert changed == {"KeyColumns": "AccountNumber, DataDate", "TimeColumns": "DataDate",
                       "BusinessDomain": "Karlılık ve Fiyatlama"}
    assert align_object({**record, **changed}, ["AccountNumber", "DataDate"], decisions) == {}


# --------------------------------------------------------------------------- decisions


def test_bundled_decisions_hold_the_owner_rules() -> None:
    decisions = load()
    assert decisions.ignores("PersonnelFlag")
    assert decisions.excludes("CUS", "prm_Something") and decisions.excludes("Unused", "vAny")
    assert decisions.domain("Kart") == "Kart ve Harcama"
    assert set(decisions.domain_aliases.values()) <= set(decisions.business_domains)
    assert ("AccountNumber", "CustomerId") in decisions.same_value_columns


def test_parse_folds_names() -> None:
    assert parse({"ignored_columns": [" PersonnelFlag "]}).ignored_columns == frozenset({"personnelflag"})


# --------------------------------------------------------------------------- normalize


def _table(desc: str, column: dict[str, str], origins: dict[str, str] | None = None) -> MergedTable:
    row = MergedColumn({"ColumnName": "Rate", **column}, dict(origins or {}))
    record = {"ObjectDescription": desc, "KeyColumns": "Rate", "TimeColumns": "", "Grain": "Kayıt",
              "BusinessDomain": "Risk"}
    return MergedTable("EDWDM.CRP.vRate", record, {}, [row], "", False, False)


def test_normalize_cleans_model_text_and_reports_each_field() -> None:
    table = _table(
        "Faiz oranları; kapsamı iş birimi ile doğrulanmalıdır.",
        {"ColumnDescription": "Kredinin faiz oranıdır. Değer boş olabilir.", "Synonyms": "faiz oranı",
         "Summary": "Faiz oranı · Bireysel/KOBİ/Ticari"},
        {"ColumnDescription": ORIGIN_MODEL},
    )
    outcome = normalize_tables([table], {}, load())
    row = table.columns[0]
    assert table.record["ObjectDescription"] == "Kar payı oranları."
    assert table.record["BusinessDomain"] == "Risk, Tahsilat ve Hukuk"
    assert row.record["ColumnDescription"] == "Fon kullandırımının kar payı oranıdır."
    assert row.record["Summary"] == "Faiz oranı"
    assert "Değer boş olabilir." in row.kept["removed"]
    kinds = {(c.kind, c.field) for c in outcome.changes}
    assert (KIND_TABLE, "ObjectDescription") in kinds and (KIND_COLUMN, "ColumnDescription") in kinds
    assert outcome.tables == 1 and outcome.columns == 1


def test_normalize_never_touches_an_admin_edit() -> None:
    edited = "Kredinin faiz oranıdır; iş birimi ile doğrulanmalıdır."
    table = _table("Oranlar.", {"ColumnDescription": edited, "Synonyms": "x", "Summary": "y"},
                   {"ColumnDescription": ORIGIN_EDITED, "Summary": ORIGIN_EDITED})
    normalize_tables([table], {}, load())
    assert table.columns[0].record["ColumnDescription"] == edited
    assert table.columns[0].record["Summary"] == "y"


def test_normalize_twice_changes_nothing_the_second_time() -> None:
    table = _table("Faiz oranları.", {"ColumnDescription": "Leasing faizidir.", "Synonyms": "faiz",
                                      "Summary": "Faiz (ör. 5)"})
    normalize_tables([table], {}, load())
    assert normalize_tables([table], {}, load()).changes == []


def test_object_code_finds_the_view_and_its_load_procedure() -> None:
    code = {"EDWDM.CRP.vRate": "SELECT 'A'", "EDWDM.CRP.ins_Rate": "INSERT 'B'", "EDWDM.CRP.vOther": "x"}
    assert sorted(object_code(code)["edwdm.crp.vrate"]) == ["INSERT 'B'", "SELECT 'A'"]


def test_a_word_inside_a_name_keeps_its_spelling() -> None:
    """Regression: 'İşletme Kredileri Grubu' (a project type) became 'İşletme Fon kullandırımları Grubu'."""

    text = "İşletme Kredileri Grubu proje tipindeki projelerin tutarıdır. Krediler bu tutara dahildir."
    assert rules.participation_wording(text) == (
        "İşletme Kredileri Grubu proje tipindeki projelerin tutarıdır. Fon kullandırımları bu tutara dahildir."
    )


def test_the_plain_part_of_a_hedged_clause_stays() -> None:
    """Regression: 'müşteri kaydındaki şubeden alınır' went with '… farklı olabilir'."""

    text, _ = rules.remove_hedges(
        "Müşterinin şubesinin adıdır; müşteri kaydındaki şubeden alınır ve hesabın şubesinden farklı olabilir."
    )
    assert text == "Müşterinin şubesinin adıdır; müşteri kaydındaki şubeden alınır."
