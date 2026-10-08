"""Runs the parity questions on one side and dumps the nine outputs of question-analysis
Requirement 2. Shared by both sides: a side only supplies the adapter in ``Side``.

For every question and settings variant:

1. the expanded query (terms, weights, concepts, term groups, synonym hits, concept weights);
2. the rule ranking with the analyst's limit (60) and with the default limit;
3. column relevance;
4. the rule answer;
5. the hint text given to the model;
6. both steps' system and user messages, response schema and token limit;
7. the analyst answer;
8. the saved-answer keys, the prompt digest and the fingerprint;
9. the single-question Excel report (sheets, cells, styles, layout) and its file name topic.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tests.parity import dump, excel_dump
from tests.parity.fake_model import CHANGED_REASON, EMPTY_DICTIONARY, FakeAnalyst

VARIANTS: dict[str, dict[str, Any]] = {
    "defaults": {},
    "expansion_off": {"expansion.enabled": False},
    "topic_zero": {"scoring.object.topic": 0.0},
    "detail0_shortlist6": {"analyst.detail_columns": 0, "analyst.shortlist": 6},
    "pool50_threshold03": {
        "search.candidate_object_columns": 50,
        "scoring.min_candidate_score": 0.3,
    },
    "top3": {"top": 3},
}
OUTPUTS = (
    "expansion", "rank_60", "rank_default", "relevance", "rule_answer", "hints", "prompts",
    "answer", "keys", "excel",
)  # fmt: skip
ANALYST_RULE_POOL = 60
GENERATED_AT = "2026-10-08 09:30"  # both sides write the report with the same time
SAMPLING = {"model": "fake-analyst", "temperature": 0.0, "reasoning_effort": "none", "seed": 42}


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    query: str
    scenario: str


class Side(Protocol):
    """What one side supplies: its own parser, engine, port adapter and report writer."""

    def parse_dictionary(self, data: bytes) -> tuple[Any, dict[str, Any]]: ...

    def empty_dictionary(self) -> Any: ...

    def word_lists(self, terms: Sequence[Path], stopwords: Path) -> tuple[list[Any], Any]: ...

    def engine(
        self, dictionary: Any, overrides: Mapping[str, Any], groups: list[Any], stop: Any, llm: Any
    ) -> Any: ...

    def client(self, core: FakeAnalyst) -> Any: ...

    def encode(self, result: Any) -> dict[str, Any]: ...

    def fingerprint(self, engine: Any, top_n: int) -> str: ...

    def prompts_digest(self) -> str: ...

    def report(self, result: Any) -> bytes: ...

    def slugify(self, query: str) -> str: ...


def apply_overrides(settings: Any, overrides: Mapping[str, Any]) -> None:
    """Dotted settings keys onto a settings object; ``top`` is the answer count, not a setting."""
    for dotted, value in overrides.items():
        if dotted == "top":
            continue
        *path, name = dotted.split(".")
        target = settings
        for part in path:
            target = getattr(target, part)
        if not hasattr(target, name):
            raise KeyError(dotted)
        setattr(target, name, value)


def read_questions(path: Path) -> list[Question]:
    """``[{id, query, scenario?}]`` from YAML (both sides have PyYAML), or one question per line."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        import yaml

        items = yaml.safe_load(text) or []
        return [
            Question(str(i["id"]), str(i["query"]), str(i.get("scenario", "normal"))) for i in items
        ]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [Question(f"r{n:03d}", line, "normal") for n, line in enumerate(lines, 1)]


def jsonl_rows(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def dictionary_dump(
    version: str,
    digest: str,
    objects: Sequence[Mapping[str, str]],
    columns: Sequence[Mapping[str, str]],
    import_warnings: Sequence[str],
    dictionary: Any,
) -> dict[str, Any]:
    """A side's parse of the workbook: the stored records, version, digest and warnings, and
    the dictionary the engine gets (columns in order with their ids, profiles)."""
    return {
        "version": version,
        "digest": digest,
        "column_count": len(dictionary.columns),
        "object_count": len(dictionary.object_keys),
        "import_warnings": list(import_warnings),
        "records": {"objects": dump.plain(objects), "columns": dump.plain(columns)},
        "dictionary": {
            "source": Path(dictionary.source_path).name,
            "version": dictionary.version,
            "warnings": list(dictionary.warnings),
            "columns": dump.plain(dictionary.columns),
            "profiles": dump.pairs(dictionary.objects),
        },
    }


def run(
    side: Side,
    workbook: bytes,
    questions: Sequence[Question],
    terms: Sequence[Path],
    stopwords: Path,
) -> Iterator[dict[str, Any]]:
    """Yields the dictionary parse, the word lists, then one record per question and variant
    with every output as plain data."""
    dictionary, parsed = side.parse_dictionary(workbook)
    yield {"record": "dictionary", "data": parsed}
    groups, stop = side.word_lists(terms, stopwords)
    words = {"terms": dump.plain(groups), "stopwords": dump.plain(stop)}
    yield {"record": "word_lists", "data": words}
    core = FakeAnalyst()
    llm = side.client(core)
    empty = side.empty_dictionary()
    for variant, overrides in VARIANTS.items():
        engine = side.engine(dictionary, overrides, groups, stop, llm)
        empty_engine = side.engine(empty, overrides, groups, stop, llm)
        top_n = int(overrides.get("top", 5))
        for q in questions:
            e = empty_engine if q.scenario == EMPTY_DICTIONARY else engine
            core.begin(q.query, q.scenario)
            outputs = _outputs(side, e, core, q, top_n, excel_dump.workbook)
            yield {"record": "outputs", "question": q.id, "variant": variant, "outputs": outputs}


def _outputs(
    side: Side,
    engine: Any,
    core: FakeAnalyst,
    q: Question,
    top_n: int,
    read_report: Callable[[bytes, str], Any],
) -> dict[str, Any]:
    ranked, expanded = engine.rank_objects(q.query, limit=ANALYST_RULE_POOL)
    ranked_default, _ = engine.rank_objects(q.query)
    relevance = engine._column_relevance(expanded)
    catalog, _ = engine._analyst_parts()
    hints = engine._hints(ranked, relevance, catalog)
    rule = side.encode(engine.rule_answer(q.query, top_n))
    result = engine.analyze(q.query, top_n)
    reason = result.fallback if q.scenario in CHANGED_REASON else ""
    text_key, meaning_key = engine.cache_keys(q.query)
    result.generated_at = GENERATED_AT
    return {
        "expansion": dump.expansion(expanded),
        "rank_60": dump.ranking(ranked),
        "rank_default": dump.ranking(ranked_default),
        "relevance": dump.pairs(relevance),
        "rule_answer": dump.answer(rule),
        "hints": hints,
        "prompts": dump.calls(core.calls),
        "answer": dump.answer(side.encode(result), mask_reason=reason),
        "keys": {
            "text_key": text_key,
            "meaning_key": meaning_key,
            "prompts_digest": side.prompts_digest(),
            "fingerprint": side.fingerprint(engine, top_n),
        },
        "excel": {
            "topic": side.slugify(q.query),
            "workbook": read_report(side.report(result), reason),
        },
    }


def write(records: Iterator[dict[str, Any]], out: Path, *, digests: bool) -> int:
    """One canonical JSON line per record; with ``digests`` each output is its SHA-256."""
    n = 0
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            if digests:
                if rec["record"] == "outputs":
                    rec = {**rec, "outputs": {k: dump.digest(v) for k, v in rec["outputs"].items()}}
                elif rec["record"] == "dictionary":
                    summary = {
                        k: rec["data"][k] for k in ("version", "column_count", "object_count")
                    }
                    rec = {**rec, "data": dump.digest(rec["data"]), "summary": summary}
                else:
                    rec = {**rec, "data": dump.digest(rec["data"])}
            fh.write(dump.canonical(rec) + "\n")
            n += 1
    return n


def main(side: Side) -> int:
    """The side's command line: run the questions and write the outputs (digests by default)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--terms", type=Path, action="append", required=True)
    parser.add_argument("--stopwords", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--full", action="store_true", help="every output in full, not digests")
    args = parser.parse_args()
    records = run(
        side,
        args.workbook.read_bytes(),
        read_questions(args.questions),
        args.terms,
        args.stopwords,
    )
    write(records, args.out, digests=not args.full)
    return 0
