"""The score card an admin decides on: every check of an update in one place.

* Mechanical checks run on every row of the candidate: no doubt or hedge in a field Navigator
  reads, no empty description, search terms that are not the description, key and time columns
  the object has, no ignored column. Any violation is a blocker.
* The verifier's sample estimates how many changed texts are misleading (with a 95% interval).
* The model's failed calls and the rows the rules had to clean say how the model behaved.

The score is 0-100: the verifier's share of usable texts, lowered for failed calls and for each
mechanical check that failed. The verdict is a recommendation; the admin approves or rejects.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.dictionary_curation.decisions import Decisions
from app.services.dictionary_curation.judge import (
    VERDICT_MINOR,
    VERDICT_RIGHT,
    VERDICT_WRONG,
    JudgeOutcome,
)
from app.services.dictionary_curation.object_rules import present_columns
from app.services.dictionary_curation.text_rules import DOUBT, HEDGE, split_terms
from app.services.dictionary_sync_merge import MergedColumn, MergedTable, fold

APPROVE = "onaylanabilir"
REVIEW = "incelenmeli"
REJECT = "reddedilmeli"
APPROVE_AT = 90
REVIEW_AT = 75
CHECK_PENALTY = 10
EXAMPLES = 5


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if not total:
        return 0.0, 0.0
    p = hits / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0.0, centre - half), min(1.0, centre + half)


def mechanical_checks(
    tables: Sequence[MergedTable], decisions: Decisions
) -> dict[str, dict[str, Any]]:
    found: dict[str, list[str]] = {
        "belirsizlik": [],
        "bos_aciklama": [],
        "aciklama_es_anlamli": [],
        "olmayan_anahtar_kolon": [],
        "olmayan_zaman_kolonu": [],
        "haric_kolon": [],
    }
    for table in tables:
        names = [c.record["ColumnName"] for c in table.columns]
        record = table.record
        if DOUBT.search(record.get("ObjectDescription", "")) or HEDGE.search(
            record.get("ObjectDescription", "")
        ):
            found["belirsizlik"].append(table.key)
        for field, check in (
            ("KeyColumns", "olmayan_anahtar_kolon"),
            ("TimeColumns", "olmayan_zaman_kolonu"),
        ):
            listed = split_terms(record.get(field, ""))
            if len(present_columns(record.get(field, ""), names)) != len(
                {n.casefold() for n in listed}
            ):
                found[check].append(table.key)
        for column in table.columns:
            row = column.record
            label = f"{table.key}.{row['ColumnName']}"
            text = row.get("ColumnDescription", "")
            fields = (text, row.get("Summary", ""), row.get("Synonyms", ""))
            if any(DOUBT.search(f) or HEDGE.search(f) for f in fields):
                found["belirsizlik"].append(label)
            if not text.strip():
                found["bos_aciklama"].append(label)
            if (
                text
                and row.get("Synonyms", "").strip().rstrip(".")[:40]
                == text.strip().rstrip(".")[:40]
            ):
                found["aciklama_es_anlamli"].append(label)
            if decisions.ignores(row["ColumnName"]):
                found["haric_kolon"].append(label)
    return {
        name: {"count": len(items), "examples": items[:EXAMPLES]} for name, items in found.items()
    }


def score_card(
    tables: Sequence[MergedTable],
    decisions: Decisions,
    judged: JudgeOutcome | None,
    *,
    model_calls: int,
    model_failures: int,
    normalized: int,
    scope: dict[str, int],
) -> dict[str, Any]:
    checks = mechanical_checks(tables, decisions)
    failed = [name for name, item in checks.items() if item["count"]]
    sample = len(judged.verdicts) if judged else 0
    wrong = sum(v["verdict"] == VERDICT_WRONG for v in judged.verdicts) if judged else 0
    low, high = wilson(wrong, sample)
    usable = 1 - wrong / sample if sample else 1.0
    failure_rate = model_failures / model_calls if model_calls else 0.0
    score = round(max(0.0, 100 * usable * (1 - failure_rate) - CHECK_PENALTY * len(failed)))
    verdict = _verdict(score, failed, sample, scope.get("scope_columns", 0))
    return {
        "score": score,
        "verdict": verdict,
        "checks": checks,
        "failed_checks": failed,
        "judge": {
            "sample": sample,
            "population": judged.population if judged else 0,
            "right": sum(v["verdict"] == VERDICT_RIGHT for v in judged.verdicts) if judged else 0,
            "minor": sum(v["verdict"] == VERDICT_MINOR for v in judged.verdicts) if judged else 0,
            "wrong": wrong,
            "wrong_interval": [round(low, 3), round(high, 3)],
            "failures": judged.failures if judged else 0,
            "wrong_rows": (
                [v for v in judged.verdicts if v["verdict"] == VERDICT_WRONG] if judged else []
            ),
        },
        "model": {
            "calls": model_calls,
            "failures": model_failures,
            "failure_rate": round(failure_rate, 3),
        },
        "rules": {"normalized_fields": normalized},
        "scope": scope,
    }


def _verdict(score: int, failed: Sequence[str], sample: int, scope_columns: int) -> str:
    if failed or score < REVIEW_AT:
        return REJECT if score < REVIEW_AT else REVIEW
    return APPROVE if score >= APPROVE_AT and (sample or not scope_columns) else REVIEW


def tables_of(
    objects: Sequence[Mapping[str, str]], columns: Sequence[Mapping[str, str]]
) -> list[MergedTable]:
    """A version's records as tables, for the mechanical checks."""

    tables: dict[str, MergedTable] = {}
    for record in objects:
        key = fold(
            f"{record.get('DatabaseName', '')}.{record.get('SchemaName', '')}.{record.get('ObjectName', '')}"
        )
        tables[key] = MergedTable(key, dict(record), {}, [], "", False, False)
    for record in columns:
        key = fold(
            f"{record.get('DatabaseName', '')}.{record.get('SchemaName', '')}.{record.get('ObjectName', '')}"
        )
        if key in tables:
            tables[key].columns.append(MergedColumn(dict(record), {}))
    return list(tables.values())


def rescored(
    card: Mapping[str, Any], tables: Sequence[MergedTable], decisions: Decisions
) -> dict[str, Any]:
    """The card again after an admin's edit: new mechanical checks, the same verifier sample."""

    if "score" not in card:
        return dict(card)
    checks = mechanical_checks(tables, decisions)
    failed = [name for name, item in checks.items() if item["count"]]
    before = int(card["score"]) + CHECK_PENALTY * len(card.get("failed_checks", []))
    score = max(0, before - CHECK_PENALTY * len(failed))
    judge = card.get("judge") or {}
    scope = card.get("scope") or {}
    verdict = _verdict(
        score, failed, int(judge.get("sample", 0)), int(scope.get("scope_columns", 0))
    )
    return {
        **card,
        "score": score,
        "verdict": verdict,
        "checks": checks,
        "failed_checks": failed,
    }
