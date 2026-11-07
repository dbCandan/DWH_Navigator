"""What an update looks at: new rows, rows whose source text changed, rows whose computation changed."""

from __future__ import annotations

from app.services.dictionary_curation.scope import (
    REASON_CODE,
    REASON_NEW_COLUMN,
    REASON_NEW_TABLE,
    REASON_SOURCE,
    plan_scope,
)
from app.services.dictionary_sync_merge import MergedColumn, MergedTable

VIEW = "EDWDM.CRP.vRate"
CODE = {
    VIEW: "CREATE VIEW CRP.vRate AS SELECT R.RateId, R.Amount * 100 AS RatePct FROM EDW.CRP.Rate R WHERE R.Active = 1",
}


def _table(*, new_table: bool = False, needs_model: bool = False, new_columns: tuple[str, ...] = ()) -> MergedTable:
    columns = [MergedColumn({"ColumnName": n}, {}, is_new=n in new_columns) for n in ("RateId", "RatePct")]
    return MergedTable(VIEW, {"ObjectKey": VIEW}, {}, columns, "", needs_model, new_table)


def _digests(code: dict[str, str]) -> dict[tuple[str, str], str]:
    return plan_scope([_table()], code, {}).digests


def test_the_first_run_records_a_baseline_and_looks_at_nothing() -> None:
    scope = plan_scope([_table()], CODE, {})
    assert scope.empty and scope.baseline == 2
    assert len(scope.digests) == 2


def test_nothing_changed_nothing_in_scope() -> None:
    scope = plan_scope([_table()], CODE, _digests(CODE))
    assert scope.empty and scope.baseline == 0


def test_reformatted_code_brings_nothing_into_scope() -> None:
    reformatted = {VIEW: CODE[VIEW].replace(" AS SELECT ", "\nAS\n  SELECT\n    ").replace(", ", ",\n    ")}
    assert plan_scope([_table()], reformatted, _digests(CODE)).empty


def test_a_changed_computation_brings_only_that_column() -> None:
    changed = {VIEW: CODE[VIEW].replace("R.Amount * 100", "R.Amount * 1000")}
    scope = plan_scope([_table()], changed, _digests(CODE))
    assert scope.columns == {("edwdm.crp.vrate", "ratepct"): REASON_CODE}


def test_a_changed_filter_brings_every_column_of_the_object() -> None:
    changed = {VIEW: CODE[VIEW].replace("R.Active = 1", "R.Active = 0")}
    scope = plan_scope([_table()], changed, _digests(CODE))
    assert set(scope.columns) == {("edwdm.crp.vrate", "rateid"), ("edwdm.crp.vrate", "ratepct")}


def test_new_table_and_new_column_and_changed_source() -> None:
    assert plan_scope([_table(new_table=True)], CODE, {}).tables == {"edwdm.crp.vrate": REASON_NEW_TABLE}
    scope = plan_scope([_table(new_columns=("RatePct",))], CODE, _digests(CODE))
    assert scope.columns == {("edwdm.crp.vrate", "ratepct"): REASON_NEW_COLUMN}
    assert plan_scope([_table(needs_model=True)], CODE, _digests(CODE)).tables == {
        "edwdm.crp.vrate": REASON_SOURCE
    }


def test_a_run_without_code_keeps_the_stored_digests() -> None:
    scope = plan_scope([_table()], {}, _digests(CODE))
    assert scope.empty and scope.digests == {}


def test_scope_keeps_the_trail_for_the_model() -> None:
    scope = plan_scope([_table()], CODE, {})
    assert any("Amount" in step for step in scope.evidence[("edwdm.crp.vrate", "ratepct")])
    assert any("Active" in f for f in scope.evidence[("edwdm.crp.vrate", "")])
