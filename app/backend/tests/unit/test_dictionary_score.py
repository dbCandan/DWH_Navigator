"""The score card and the verifier an admin decides on."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from app.services.dictionary_curation.decisions import load
from app.services.dictionary_curation.judge import (
    VERDICT_RIGHT,
    VERDICT_WRONG,
    JudgeOutcome,
    judge_request,
    judge_rows,
    sample_rows,
)
from app.services.dictionary_curation.score import (
    APPROVE,
    REJECT,
    REVIEW,
    mechanical_checks,
    score_card,
    wilson,
)
from app.services.dictionary_sync_merge import MergedColumn, MergedTable


def _table(**column: str) -> MergedTable:
    record = {
        "ColumnName": "Amount",
        "ColumnDescription": "Tutardır.",
        "Synonyms": "tutar",
        "Summary": "Tutar",
        **column,
    }
    other = MergedColumn(
        {
            "ColumnName": "DataDate",
            "ColumnDescription": "Veri tarihidir.",
            "Synonyms": "tarih",
            "Summary": "Tarih",
        },
        {},
    )
    return MergedTable(
        "EDWDM.CRP.vRate",
        {
            "ObjectDescription": "Oranlar.",
            "KeyColumns": "Amount, DataDate",
            "TimeColumns": "DataDate",
        },
        {},
        [MergedColumn(record, {}), other],
        "",
        False,
        False,
    )


def test_a_clean_candidate_passes_every_check() -> None:
    checks = mechanical_checks([_table()], load())
    assert all(item["count"] == 0 for item in checks.values())


def test_each_check_finds_its_violation() -> None:
    tables = [
        _table(ColumnDescription="Tutar olabilir."),
        _table(ColumnDescription=""),
        _table(Synonyms="Tutardır"),
        _table(ColumnName="PersonnelFlag"),
    ]
    tables.append(
        MergedTable(
            "EDWDM.CRP.vX",
            {"KeyColumns": "Missing", "TimeColumns": "Gone"},
            {},
            [],
            "",
            False,
            False,
        )
    )
    checks = mechanical_checks(tables, load())
    for name in (
        "belirsizlik",
        "bos_aciklama",
        "aciklama_es_anlamli",
        "haric_kolon",
        "olmayan_anahtar_kolon",
        "olmayan_zaman_kolonu",
    ):
        assert checks[name]["count"] >= 1, name


def _judged(right: int, wrong: int) -> JudgeOutcome:
    verdicts = [
        {"table": "t", "column": f"c{i}", "verdict": VERDICT_RIGHT, "reason": ""}
        for i in range(right)
    ]
    verdicts += [
        {"table": "t", "column": f"w{i}", "verdict": VERDICT_WRONG, "reason": "x"}
        for i in range(wrong)
    ]
    return JudgeOutcome(verdicts=verdicts, calls=right + wrong, population=100)


def _card(
    judged: JudgeOutcome | None,
    tables: list[MergedTable] | None = None,
    failures: int = 0,
) -> dict[str, Any]:
    return score_card(
        tables or [_table()],
        load(),
        judged,
        model_calls=40,
        model_failures=failures,
        normalized=3,
        scope={"scope_columns": 40},
    )


def test_score_and_verdict() -> None:
    assert _card(_judged(39, 1))["verdict"] == APPROVE
    assert _card(_judged(32, 8))["verdict"] == REVIEW
    assert _card(_judged(20, 20))["verdict"] == REJECT
    failed = _card(_judged(40, 0), tables=[_table(ColumnDescription="Tutar olabilir.")])
    assert (
        failed["failed_checks"] == ["belirsizlik"]
        and failed["verdict"] == REVIEW
        and failed["score"] == 90
    )


def test_no_verifier_sample_never_approves_by_itself() -> None:
    assert _card(None)["verdict"] == REVIEW


def test_wrong_rows_and_interval_are_on_the_card() -> None:
    card = _card(_judged(36, 4))
    assert card["judge"]["wrong"] == 4 and len(card["judge"]["wrong_rows"]) == 4
    low, high = card["judge"]["wrong_interval"]
    assert low < 0.1 < high


def test_wilson_interval() -> None:
    low, high = wilson(7, 300)
    assert round(low, 3) == 0.011 and round(high, 3) == 0.047
    assert wilson(0, 0) == (0.0, 0.0)


def test_sample_is_reproducible_and_bounded() -> None:
    tables = [_table()]
    rows = [("edwdm.crp.vrate", "amount"), ("edwdm.crp.vrate", "datadate")]
    assert sample_rows(tables, rows, 1, "seed") == sample_rows(tables, rows, 1, "seed")
    assert len(sample_rows(tables, rows, 5, "seed")) == 2


def test_judge_counts_unusable_answers_as_failures() -> None:
    answers = iter([{"aciklama": "dogru", "neden": ""}, {"aciklama": "belki"}, None])

    async def chat(_request: Any) -> Any:
        value = next(answers)
        return SimpleNamespace(ok=value is not None, value=value)

    table = _table()
    chosen = [(table, c) for c in table.columns] + [(table, table.columns[0])]
    outcome = asyncio.run(judge_rows(chosen, chat, {}, population=3))
    assert len(outcome.verdicts) == 1 and outcome.failures == 2 and outcome.calls == 3


def test_judge_request_carries_the_trail_and_says_it_did_not_write_the_text() -> None:
    table = _table()
    request = judge_request(table, table.columns[0], ["SUM(Amount)"])
    assert "Sözlüğü sen yazmadın" in request.system and "SUM(Amount)" in request.user
