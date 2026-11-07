"""Typo correction against the catalog (011-dictionary-sync, "Yazım düzeltme"); no driver."""

import pytest

from app.domain.dictionary_source import SourceColumn, SourceTable
from app.infrastructure.dictionary_source.name_matching import (
    _is_single_edit,
    match_names,
    normal_form,
    reconcile,
)

pytestmark = pytest.mark.unit


def edit(source: str, *catalog: str) -> str | None:
    return match_names([source], catalog, single_edit=True)[source]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Customer ", "customer"),
        ("Cust omer", "customer"),
        ("Customer ", "customer"),
        ("Cus\u200btomer", "customer"),
        ("﻿Customer", "customer"),
        ("Customer.", "customer"),
        ("Customer,", "customer"),
        ("'Customer';", "customer"),
        ("`Customer`:", "customer"),
        ('"Customer"', "customer"),
        ("Customer . ", "customer"),
        ("Cust.omer", "cust.omer"),
    ],
)
def test_normal_form(source: str, expected: str) -> None:
    assert normal_form(source) == expected


def test_exact_match_is_never_touched() -> None:
    assert match_names(["Customer"], ["Customer", "CUSTOMER"]) == {"Customer": "Customer"}


@pytest.mark.parametrize(
    "source",
    ["Customer ", "Cust omer", "Customer.", "Customer,", "CUSTOMER", "customer"],
)
def test_normal_form_step_takes_catalog_spelling(source: str) -> None:
    assert match_names([source], ["Customer"]) == {source: "Customer"}


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("Customerr", "extra letter"),
        ("Custmer", "missing letter"),
        ("Cutsomer", "transposition"),
        ("Custamer", "substitution"),
        ("Cust_omer", "extra separator"),
        ("custmer.", "with normal form"),
    ],
)
def test_single_edit_is_corrected(source: str, kind: str) -> None:
    assert edit(source, "Customer", "Invoice") == "Customer", kind


def test_single_edit_needs_the_flag() -> None:
    assert match_names(["Custmer"], ["Customer"]) == {"Custmer": None}


@pytest.mark.parametrize(
    ("source", "catalog"),
    [
        ("Risk1", "Risk2"),
        ("RiskScore1", "RiskScore2"),
        ("RiskScore1", "RiskScore"),
        ("RiskScore", "RiskScore1"),
        ("RiskScore11", "RiskScore1"),
        ("Risk12Score", "Risk21Score"),
        ("RiskScorea", "RiskScore1"),
    ],
)
def test_digit_guard(source: str, catalog: str) -> None:
    assert edit(source, catalog) is None


def test_digits_outside_the_edit_are_allowed() -> None:
    assert edit("Custmer1", "Customer1") == "Customer1"


def test_two_edits_are_not_corrected() -> None:
    assert edit("Custmr", "Customer") is None


def test_ambiguous_candidates_stay_uncorrected() -> None:
    assert edit("Customerz", "Customer", "Customers") is None


def test_ambiguous_normal_form_does_not_fall_through() -> None:
    assert match_names(["CUSTOMER"], ["Customer", "customer"], single_edit=True) == {
        "CUSTOMER": None
    }


def test_candidate_taken_by_exact_row() -> None:
    result = match_names(["Customer", "Custmer"], ["Customer"], single_edit=True)
    assert result == {"Customer": "Customer", "Custmer": None}


def test_normal_form_candidate_taken_by_exact_row() -> None:
    result = match_names(["Customer", "Customer."], ["Customer"])
    assert result == {"Customer": "Customer", "Customer.": None}


def test_two_rows_competing_both_stay_uncorrected() -> None:
    result = match_names(["Custmer", "Customr"], ["Customer"], single_edit=True)
    assert result == {"Custmer": None, "Customr": None}


def test_normal_form_and_single_edit_rows_compete() -> None:
    result = match_names(["Customer.", "Custmer"], ["Customer"], single_edit=True)
    assert result == {"Customer.": None, "Custmer": None}


def test_case_variants_are_one_row_not_rivals() -> None:
    result = match_names(["CUSTOMER", "customer"], ["Customer"])
    assert result == {"CUSTOMER": "Customer", "customer": "Customer"}
    assert match_names(["Customer", "customer"], ["Customer"])["customer"] == "Customer"


@pytest.mark.parametrize(
    ("source", "catalog"),
    [("Cstmr", "Cstmer"), ("Custm", "Custom"), ("Abcde", "Abcdf"), ("Abcdef", "Abcde")],
)
def test_names_shorter_than_six_are_not_edited(source: str, catalog: str) -> None:
    assert edit(source, catalog) is None


def test_six_letters_is_enough() -> None:
    assert edit("Abcdeg", "Abcdef") == "Abcdef"


def test_shared_names_ignore_exclusivity() -> None:
    result = match_names(["EDWDM", "EDWDM."], ["EDWDM"], exclusive=False)
    assert result == {"EDWDM": "EDWDM", "EDWDM.": "EDWDM"}


def test_punctuation_only_name_matches_nothing() -> None:
    assert edit("...", "Customer") is None


# --- reconcile -----------------------------------------------------------------------------------

CATALOGS = {"DB": {"dbo": {"Customer": {"CustomerId", "FullName"}, "Invoice": {"InvoiceId"}}}}
DATABASES = {"DB": "DB"}


def table(name: str, description: str = "d", schema: str = "dbo", db: str = "DB") -> SourceTable:
    return SourceTable(db, schema, name, description)


def column(
    table_name: str,
    name: str,
    description: str = "c",
    group: str = "g",
    schema: str = "dbo",
    db: str = "DB",
) -> SourceColumn:
    return SourceColumn(db, schema, table_name, name, description, group)


def test_definition_and_detail_reach_the_same_corrected_table() -> None:
    snapshot = reconcile(
        [table("Custmer", "from definition")],
        [column("Custmer", "CustomerId"), column("CUSTMER", "FullName")],
        DATABASES,
        CATALOGS,
    )
    assert snapshot.tables == (SourceTable("DB", "dbo", "Customer", "from definition"),)
    assert {row.table for row in snapshot.columns} == {"Customer"}
    assert snapshot.corrected_tables == (("DB.dbo.Custmer", "DB.dbo.Customer"),)
    assert snapshot.excluded_tables == ()


def test_corrected_rows_dedupe_after_correction() -> None:
    snapshot = reconcile(
        [table("Customer")],
        [
            column("Customer", "FULLNAME", description=""),
            column("Customer", "fullname", description="kept"),
            column("Customer", "CustomerId"),
        ],
        DATABASES,
        CATALOGS,
    )
    assert [(row.name, row.description) for row in snapshot.columns] == [
        ("CustomerId", "c"),
        ("FullName", "kept"),
    ]
    assert snapshot.skipped == 1
    assert snapshot.corrected_columns == (
        ("DB.dbo.Customer", "FULLNAME", "FullName"),
        ("DB.dbo.Customer", "fullname", "FullName"),
    )


def test_column_is_only_matched_inside_its_object() -> None:
    snapshot = reconcile(
        [table("Customer")],
        [column("Customer", "CustomerId"), column("Customer", "InvoicId")],
        DATABASES,
        CATALOGS,
    )
    assert snapshot.excluded_columns == (("DB.dbo.Customer", "InvoicId"),)
    assert snapshot.corrected_columns == ()


def test_object_is_only_matched_inside_its_schema() -> None:
    catalogs = {"DB": {"dbo": {"Other": {"Id"}}, "stg": {"Customer": {"Id"}}}}
    snapshot = reconcile([], [column("Custmer", "Id")], DATABASES, catalogs)
    assert snapshot.tables == ()
    assert snapshot.excluded_tables == ("DB.dbo.Custmer",)


def test_schema_gets_the_normal_form_only() -> None:
    corrected = reconcile([], [column("Customer", "FullName", schema="DBO ")], DATABASES, CATALOGS)
    assert corrected.corrected_tables == (("DB.DBO .Customer", "DB.dbo.Customer"),)
    assert corrected.columns[0].schema == "dbo"

    # A misspelled schema is not fuzzy-matched; the object is found by its name instead.
    catalogs = {"DB": {"dbosch": {"Customer": {"FullName"}}}}
    typo = reconcile([], [column("Customer", "FullName", schema="dbsch")], DATABASES, catalogs)
    assert typo.corrected_tables == (("DB.dbsch.Customer", "DB.dbosch.Customer"),)


def test_many_tables_share_a_corrected_schema_and_database() -> None:
    snapshot = reconcile(
        [],
        [column("Customer", "FullName", db="db."), column("Invoice", "InvoiceId", db="db.")],
        {"db.": "DB"},
        CATALOGS,
    )
    assert [row.name for row in snapshot.tables] == ["Customer", "Invoice"]
    assert {row.database for row in snapshot.columns} == {"DB"}


def test_excluded_column_is_reported_under_the_catalog_key() -> None:
    snapshot = reconcile(
        [table("Custmer")],
        [column("Custmer", "CustomerId"), column("Custmer", "Nope")],
        DATABASES,
        CATALOGS,
    )
    assert snapshot.excluded_columns == (("DB.dbo.Customer", "Nope"),)


def test_rows_of_unreachable_databases_are_left_out() -> None:
    snapshot = reconcile([table("Customer", db="X")], [column("Customer", "Id", db="X")], {}, {})
    assert snapshot.tables == () and snapshot.excluded_tables == () and snapshot.skipped == 0


def test_a_view_is_never_corrected_to_the_table_behind_it() -> None:
    assert _is_single_edit("vcardlimit", "cardlimit") is False
    assert _is_single_edit("cardlimit", "vcardlimit") is False
    assert _is_single_edit("xcardlimit", "vcardlimit") is False
    assert _is_single_edit("vcardlimitt", "vcardlimit") is True


def test_a_procedure_is_confirmed_by_name_and_keeps_its_columns() -> None:
    snapshot = reconcile(
        (SourceTable("EDWBridge", "AIS", "rpt_Loyalty", "Rapor"),),
        (
            SourceColumn("EDWBridge", "AIS", "rpt_Loyalty", "Period", "Dönem", "Grup"),
            SourceColumn("EDWBridge", "AIS", "rpt_Loyalty", "PERIOD", "", "Grup"),
        ),
        {"EDWBridge": "EDWBridge"},
        {"EDWBridge": {"AIS": {"rpt_Loyalty": None}}},
    )
    assert [c.name for c in snapshot.columns] == ["Period"]
    assert snapshot.excluded_columns == ()
    assert snapshot.excluded_tables == ()


def _located(source_schema: str, catalog: dict) -> tuple:
    snapshot = reconcile(
        (SourceTable("EDWDM", source_schema, "vPayback", "Plan"),),
        (SourceColumn("EDWDM", source_schema, "vPayback", "PlanId", "Plan no", "Grup"),),
        {"EDWDM": "EDWDM"},
        {"EDWDM": catalog},
    )
    return snapshot.tables, snapshot.corrected_tables, snapshot.excluded_tables


def test_an_object_under_the_wrong_schema_moves_and_keeps_its_name() -> None:
    tables, corrected, excluded = _located(
        "PRC", {"PRC": {"vOther": ["A"]}, "CFM": {"vPayback": ["PlanId"]}}
    )
    assert [(t.schema, t.name) for t in tables] == [("CFM", "vPayback")]
    assert corrected == (("EDWDM.PRC.vPayback", "EDWDM.CFM.vPayback"),)
    assert excluded == ()


def test_a_name_found_in_two_other_schemas_is_left_out() -> None:
    tables, _, excluded = _located(
        "PRC", {"CFM": {"vPayback": ["PlanId"]}, "CON": {"vPayback": ["PlanId"]}}
    )
    assert tables == ()
    assert excluded == ("EDWDM.PRC.vPayback",)


def test_the_schema_step_never_changes_a_name() -> None:
    tables, _, excluded = _located("PRC", {"CFM": {"vPaybackPlan": ["PlanId"]}})
    assert tables == ()
    assert excluded == ("EDWDM.PRC.vPayback",)


def test_a_confirmed_alias_reaches_a_name_no_rule_would_touch() -> None:
    snapshot = reconcile(
        (SourceTable("EDWBridge", "TRX", "rpt_HighCash", "Rapor"),),
        (SourceColumn("EDWBridge", "TRX", "rpt_HighCash", "Id", "No", "Grup"),),
        {"EDWBridge": "EDWBridge"},
        {"EDWBridge": {"TRX": {"rpt_EDWHighCash": None}}},
        {"EDWBridge.TRX.rpt_HighCash": "EDWBridge.TRX.rpt_EDWHighCash"},
    )
    assert [t.name for t in snapshot.tables] == ["rpt_EDWHighCash"]
    assert snapshot.corrected_tables == (
        ("EDWBridge.TRX.rpt_HighCash", "EDWBridge.TRX.rpt_EDWHighCash"),
    )
