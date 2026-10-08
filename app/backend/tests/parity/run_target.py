"""The target side of the parity test: ``app.services.analysis`` in the backend environment.

The term groups and stopwords are read from the seed lists the way the vocabulary seed
migration keeps them (rows as they are, in file order) and the engine's reading turns them
into ``TermGroup`` and stopword forms (vocabulary-management Requirement 2 and 9).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.domain.analysis import Dictionary, TermGroup
from app.services.analysis import answer_cache
from app.services.analysis.config import Settings
from app.services.analysis.dictionary_workbook import (
    empty_dictionary,
    from_workbook,
    load_dictionary,
)
from app.services.analysis.llm.port import FailureCode, ModelFailure, ModelSampling
from app.services.analysis.pipeline import Engine, Resources
from app.services.analysis.report.excel import slugify, write_ask_report
from app.services.analysis.text.normalize import load_stopwords
from tests.parity import fake_model
from tests.parity.driver import (
    SAMPLING,
    apply_overrides,
    dictionary_dump,
    jsonl_rows,
    main,
)

_CHAT_FAILURES = {
    fake_model.FAIL_INVALID_JSON: ModelFailure(FailureCode.INVALID_JSON),
    fake_model.FAIL_CONTEXT: ModelFailure(FailureCode.CONTEXT_EXCEEDED, 400),
    fake_model.FAIL_TIMEOUT: ModelFailure(FailureCode.TIMEOUT),
    fake_model.FAIL_CONNECTION: ModelFailure(FailureCode.CONNECT_REFUSED),
    fake_model.FAIL_HTTP_500: ModelFailure(FailureCode.UPSTREAM_STATUS, 500),
}
_HEALTH_FAILURES = {
    fake_model.DOWN_CONNECT: ModelFailure(FailureCode.CONNECT_REFUSED),
    fake_model.DOWN_UNAUTHORIZED: ModelFailure(FailureCode.UNAUTHORIZED, 401),
}


class TargetClient:
    """The fake core behind the target's model port."""

    def __init__(self, core: fake_model.FakeAnalyst) -> None:
        self.core = core
        self.last_failure: ModelFailure | None = None

    @property
    def available(self) -> bool:
        return self.core.available

    @property
    def model(self) -> str:
        return self.core.model

    def health(self) -> ModelFailure | None:
        kind = self.core.health()
        return _HEALTH_FAILURES[kind] if kind else None

    def chat_json(
        self, system: str, user: str, schema: Mapping[str, Any], *, max_tokens: int = 1024
    ) -> dict[str, Any] | None:
        reply, failure = self.core.reply(system, user, schema, max_tokens)
        if failure:
            self.last_failure = _CHAT_FAILURES[failure]
        return reply


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def term_groups(rows: Sequence[Mapping[str, Any]]) -> list[TermGroup]:
    groups: list[TermGroup] = []
    for row in rows:
        term = _text(row.get("term"))
        if not term:
            continue
        raw = row.get("equivalents")
        items = raw if isinstance(raw, list) else []
        equivalents = tuple(e for e in map(_text, items) if e)
        groups.append(
            TermGroup(term, equivalents, _text(row.get("domain")), _text(row.get("note")))
        )
    return groups


class TargetSide:
    def parse_dictionary(self, data: bytes) -> tuple[Dictionary, dict[str, Any]]:
        imported = from_workbook(data)
        d = load_dictionary(imported.objects, imported.columns, imported.version, imported.digest)
        parsed = dictionary_dump(
            imported.version,
            imported.digest,
            imported.objects,
            imported.columns,
            imported.warnings,
            d,
        )
        return d, parsed

    def empty_dictionary(self) -> Dictionary:
        return empty_dictionary()

    def word_lists(self, terms: Sequence[Path], stopwords: Path) -> tuple[list[Any], Any]:
        groups = [g for path in terms for g in term_groups(jsonl_rows(path))]
        stop = load_stopwords(_text(row.get("word")) for row in jsonl_rows(stopwords))
        return groups, stop

    def engine(
        self, dictionary: Any, overrides: Mapping[str, Any], groups: list[Any], stop: Any, llm: Any
    ) -> Engine:
        settings = Settings()
        apply_overrides(settings, overrides)
        return Engine(dictionary, settings, Resources(list(groups), stop), llm=llm)

    def client(self, core: fake_model.FakeAnalyst) -> TargetClient:
        return TargetClient(core)

    def encode(self, result: Any) -> dict[str, Any]:
        return answer_cache.encode(result)

    def fingerprint(self, engine: Any, top_n: int) -> str:
        sampling = ModelSampling(
            str(SAMPLING["model"]),
            float(SAMPLING["temperature"]),
            str(SAMPLING["reasoning_effort"]),
            int(SAMPLING["seed"]),
        )
        return str(engine.cache_fingerprint(top_n, sampling))

    def prompts_digest(self) -> str:
        return answer_cache.prompts_digest()

    def report(self, result: Any) -> bytes:
        return write_ask_report(result)

    def slugify(self, query: str) -> str:
        return slugify(query)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)  # as on the source side
    raise SystemExit(main(TargetSide()))
