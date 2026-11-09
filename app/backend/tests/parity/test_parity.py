"""Parity with the source 76e21a3 without the source copy (question-analysis Acceptance 1, 2).

The target runs the parity questions with two hash seeds and must give the source snapshot's
outputs byte for byte; the ported modules' constants must be the source's. Rebuilding the
snapshot from the source copy is ``python -m tests.parity.harness --verify-snapshot``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.parity import generate_fixtures, harness

pytestmark = pytest.mark.unit

# Constants the target leaves to the capability that ports them with its own reader.
SOURCE_ONLY = {
    "vsa.loader": {  # word lists (vocabulary-management)
        "MAX_LIST_ITEMS",
        "WORD_SHEETS",
        "_EQUIVALENT_SPLIT",
    },
    "vsa.dictionary_store": {"FORMAT"},  # the jsonl store; the target keeps it in PostgreSQL
    # Step 1 sends shortlist_schema(limit), SHORTLIST_SCHEMA with its lists capped.
    "vsa.llm.analyst": {"SHORTLIST_SCHEMA"},
}
# Allowed difference (d) of Requirement 1: the fingerprint takes the chat model from the model
# port, so of the settings only the saved-answer switches stay out of it.
CHANGED = {"vsa.answer_cache": {"_NEUTRAL": ["cache"]}}
# Target-only names: Istanbul time (Decision 13), Requirement 5 reasons, Decision 11, and the
# UTC zone of "now" in the vote weighting (the container clock is UTC, the source's was local).
TARGET_ONLY = {
    "vsa.pipeline": {"ISTANBUL", "_UNREACHABLE", "_NO_MODEL", "_KEY_UNREADABLE"},
    "vsa.dictionary_store": {"SOURCE_NAME"},
    "vsa.feedback": {"UTC"},
    "vsa.answer_cache": {"_NEUTRAL_FIELDS"},  # step 1's reply limit stays out of the key
    # Step 1's list caps, shared by the schema and the parser (a looping model filled max_tokens).
    "vsa.llm.analyst": {
        "SHORTLIST_FAMILIES",
        "SHORTLIST_FAMILY_TERMS",
        "SHORTLIST_TERMS",
    },
    "vsa.llm.analyst_prompts": {"SHORTLIST_FAMILIES", "SHORTLIST_FAMILY_TERMS", "SHORTLIST_TERMS"},
}
# Target-only settings: step 1's reply limit, a fixed 2500 in the source (a thinking model filled
# it before its JSON), is an analyst setting here.
TARGET_ONLY_SETTINGS = {"analyst": {"shortlist_max_tokens"}}


def _without_target_settings(settings: list[Any]) -> list[Any]:
    return [
        [section, [kv for kv in values if kv[0] not in TARGET_ONLY_SETTINGS.get(section, set())]]
        for section, values in settings
    ]


def test_target_matches_the_source_snapshot(tmp_path: Path) -> None:
    """Every output of every question and variant, with PYTHONHASHSEED 0 and 4242."""
    outs = harness.run_targets(tmp_path)
    for seed, out in outs.items():
        compared, diffs = harness.compare(harness.SNAPSHOT / "outputs.jsonl", out)
        assert diffs == [], f"PYTHONHASHSEED={seed}"
        assert compared == 2 + 170 * 6 * 10


def test_snapshot_was_made_from_these_inputs() -> None:
    manifest = json.loads((harness.SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == harness.manifest()
    assert manifest["questions"] >= 150


def test_constants_match_the_source() -> None:
    source = json.loads((harness.SNAPSHOT / "constants.json").read_text(encoding="utf-8"))
    target = harness.target_constants()
    assert target["prompts_digest"] == source["prompts_digest"]
    assert _without_target_settings(target["settings"]) == source["settings"]
    for module, values in source["modules"].items():
        mine = target["modules"][module]
        for name, value in values.items():
            if name in SOURCE_ONLY.get(module, set()):
                assert name not in mine, (module, name)
            elif name in CHANGED.get(module, {}):
                assert mine[name] == CHANGED[module][name], (module, name)
            else:
                assert mine.get(name) == value, (module, name)
        assert set(mine) - set(values) == TARGET_ONLY.get(module, set()), module


def test_fixtures_come_from_the_generator() -> None:
    workbook = generate_fixtures.build_workbook()
    committed = generate_fixtures.WORKBOOK.read_bytes()
    assert generate_fixtures.workbook_parts(workbook) == generate_fixtures.workbook_parts(committed)
    text = generate_fixtures.QUESTIONS.read_text(encoding="utf-8")
    assert text == generate_fixtures.questions_yaml()


def test_dictionary_and_questions_have_the_required_breadth() -> None:
    tables = generate_fixtures.tables()
    assert len(tables) >= 60 and sum(len(t.columns) for t in tables) >= 1500
    assert max(len(t.columns) for t in tables) > 90
    assert len([q for q in generate_fixtures.questions() if q[0][0] in "sx"]) >= 137


def test_comparison_names_the_question_variant_and_output(tmp_path: Path) -> None:
    lines = (harness.SNAPSHOT / "outputs.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[5])
    record["outputs"]["hints"] = "0" * 64
    changed = tmp_path / "changed.jsonl"
    changed.write_text("\n".join([*lines[:5], json.dumps(record), *lines[6:]]) + "\n", "utf-8")
    _, diffs = harness.compare(harness.SNAPSHOT / "outputs.jsonl", changed)
    assert diffs == [f"{record['question']} / {record['variant']}: hints farklı"]
    cut = tmp_path / "cut.jsonl"
    cut.write_text("\n".join(lines[:3]) + "\n", "utf-8")
    _, short = harness.compare(harness.SNAPSHOT / "outputs.jsonl", cut)
    assert short == [f"satır sayısı farklı: beklenen {len(lines)}, gelen 3"]


def test_source_copy_must_be_the_source_tree(tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    (copy / "src" / "vsa").mkdir(parents=True)
    (copy / "src" / "vsa" / "a.txt").write_bytes(b"hello\r\n")  # CRLF hashes as LF
    plain = tmp_path / "plain"
    (plain / "sub").mkdir(parents=True)
    (plain / "a.txt").write_bytes(b"hello\n")
    (plain / "sub" / "b.bin").write_bytes(b"x")
    assert harness.git_tree(plain) == "80398e1dc1ba8912939d26a238bcabb5964d2046"  # git write-tree
    with pytest.raises(harness.ParityError, match="ağaç özeti"):
        harness.verify_source_copy(copy)
    expected = harness.git_tree(copy)
    harness.verify_source_copy(copy, expected)
    (copy / "src" / "vsa" / "__pycache__").mkdir()
    (copy / "src" / "vsa" / "__pycache__" / "x.pyc").write_bytes(b"\0")
    with pytest.raises(harness.ParityError):
        harness.verify_source_copy(copy, expected)
