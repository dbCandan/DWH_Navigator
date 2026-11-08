"""What an update looks at: new rows, rows whose source text changed, rows whose computation changed."""

from __future__ import annotations

from app.services.dictionary_curation.scope import (
    GATE,
    REASON_CODE,
    REASON_NEW_COLUMN,
    REASON_NEW_TABLE,
    REASON_SOURCE,
    plan_scope,
)
from app.services.dictionary_sync_merge import MergedColumn, MergedTable

VIEW = "EDWDM.CRP.vRate"
KEY = "edwdm.crp.vrate"
CODE = {
    VIEW: "CREATE VIEW CRP.vRate AS SELECT R.RateId, R.Amount * 100 AS RatePct "
    "FROM EDW.CRP.Rate R WHERE R.Active = 1",
    "EDW.CRP.ins_Rate": "INSERT INTO EDW.CRP.Rate (RateId, Amount, Active) SELECT Id, Amt, 1 FROM STG.Rate",
}


def _table(
    *,
    new_table: bool = False,
    needs_model: bool = False,
    new_columns: tuple[str, ...] = (),
) -> MergedTable:
    columns = [
        MergedColumn({"ColumnName": n}, {}, is_new=n in new_columns)
        for n in ("RateId", "RatePct")
    ]
    return MergedTable(
        VIEW, {"ObjectKey": VIEW}, {}, columns, "", needs_model, new_table
    )


def _with(view: str | None = None, loader: str | None = None) -> dict[str, str]:
    code = dict(CODE)
    if view is not None:
        code[VIEW] = view
    if loader is not None:
        code["EDW.CRP.ins_Rate"] = loader
    return code


def _after(*codes: dict[str, str]) -> dict[tuple[str, str], str]:
    stored: dict[tuple[str, str], str] = {}
    for code in codes:
        stored = plan_scope([_table()], code, stored).digests
    return stored


def test_the_first_run_records_the_gate_only_and_traces_nothing() -> None:
    scope = plan_scope([_table()], CODE, {})
    assert scope.empty and scope.baseline == 1 and scope.traced == 0
    assert set(scope.digests) == {(KEY, GATE)}


def test_nothing_changed_nothing_traced_nothing_in_scope() -> None:
    scope = plan_scope([_table()], CODE, _after(CODE))
    assert scope.empty and scope.traced == 0 and scope.baseline == 0


def test_reformatted_code_brings_nothing_into_scope() -> None:
    view = (
        CODE[VIEW]
        .replace(" AS SELECT ", "\nAS\n  SELECT\n    ")
        .replace(", ", ",\n    ")
    )
    reformatted = _with(view=view)
    assert plan_scope([_table()], reformatted, _after(CODE)).empty


def test_the_first_change_of_an_object_brings_all_its_columns() -> None:
    changed = _with(view=CODE[VIEW].replace("R.Amount * 100", "R.Amount * 1000"))
    scope = plan_scope([_table()], changed, _after(CODE))
    assert set(scope.columns) == {(KEY, "rateid"), (KEY, "ratepct")}
    assert set(scope.columns.values()) == {REASON_CODE}


def test_a_later_change_brings_only_the_column_whose_computation_changed() -> None:
    once = _with(view=CODE[VIEW].replace("R.Amount * 100", "R.Amount * 1000"))
    twice = _with(view=CODE[VIEW].replace("R.Amount * 100", "R.Amount * 10000"))
    scope = plan_scope([_table()], twice, _after(CODE, once))
    assert scope.columns == {(KEY, "ratepct"): REASON_CODE}


def test_a_changed_load_procedure_of_a_read_table_opens_the_gate() -> None:
    once = _with(loader=CODE["EDW.CRP.ins_Rate"].replace("Amt", "Amt * 2"))
    stored = _after(
        CODE, _with(view=CODE[VIEW].replace("R.Active = 1", "R.Active = 1 "))
    )
    assert (
        plan_scope([_table()], once, stored).digests[(KEY, GATE)] != stored[(KEY, GATE)]
    )


def test_a_changed_filter_brings_every_column_of_the_object() -> None:
    once = _with(view=CODE[VIEW].replace("R.Amount * 100", "R.Amount * 1000"))
    filtered = _with(view=once[VIEW].replace("R.Active = 1", "R.Active = 0"))
    scope = plan_scope([_table()], filtered, _after(CODE, once))
    assert set(scope.columns) == {(KEY, "rateid"), (KEY, "ratepct")}


def test_new_table_and_new_column_and_changed_source() -> None:
    assert plan_scope([_table(new_table=True)], CODE, {}).tables == {
        KEY: REASON_NEW_TABLE
    }
    scope = plan_scope([_table(new_columns=("RatePct",))], CODE, _after(CODE))
    assert scope.columns == {(KEY, "ratepct"): REASON_NEW_COLUMN}
    assert any("Amount" in step for step in scope.evidence[(KEY, "ratepct")])
    assert plan_scope([_table(needs_model=True)], CODE, _after(CODE)).tables == {
        KEY: REASON_SOURCE
    }


def test_a_run_without_code_keeps_nothing_new() -> None:
    scope = plan_scope([_table()], {}, _after(CODE))
    assert scope.empty and scope.digests == {}


def test_stored_trails_are_carried_while_the_code_stays() -> None:
    once = _with(view=CODE[VIEW].replace("R.Amount * 100", "R.Amount * 1000"))
    stored = _after(CODE, once)
    assert (KEY, "ratepct") in stored
    assert plan_scope([_table()], once, stored).digests == stored


def test_ensure_evidence_traces_the_rows_the_model_will_describe() -> None:
    scope = plan_scope([_table()], CODE, _after(CODE))
    scope.ensure_evidence([_table()], {(KEY, "ratepct")})
    assert any("Amount" in step for step in scope.evidence[(KEY, "ratepct")])
    assert any("Active" in f for f in scope.evidence[(KEY, GATE)])
