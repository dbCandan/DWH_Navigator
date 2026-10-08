"""The source side of the parity test: the source package ``vsa`` from a verified copy of
commit 76e21a3, in a Python 3.12 environment with the source's locked libraries. The harness
runs it as ``python -B -m tests.parity.run_source`` with the copy's ``src`` on the path; the
source code itself is never copied into this repository.

The source reads the workbook the way its import does (``from_workbook``, ``save``,
``load_dictionary``) in a temporary folder that is removed afterwards.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from vsa import answer_cache, dictionary_store
from vsa.config import Settings
from vsa.loader import load_stopword_file, load_term_dictionary
from vsa.pipeline import Engine, Resources
from vsa.report import excel

from tests.parity import fake_model
from tests.parity.driver import SAMPLING, apply_overrides, dictionary_dump, main

# The source's own error texts for each failure kind, as its HTTP client words them.
_CHAT_ERRORS = {
    fake_model.FAIL_INVALID_JSON: "model geçerli JSON üretmedi",
    fake_model.FAIL_CONTEXT: (
        '/chat/completions: HTTP 400: {"error": {"message": "This model\'s maximum context '
        'length is 65536 tokens; the request (70212 tokens) exceeds the context size"}}'
    ),
    fake_model.FAIL_TIMEOUT: "/chat/completions: timed out",
    fake_model.FAIL_CONNECTION: "/chat/completions: <urlopen error [Errno 61] Connection refused>",
    fake_model.FAIL_HTTP_500: '/chat/completions: HTTP 500: {"error": "internal server error"}',
}
_HEALTH_ERRORS = {
    "": "",
    fake_model.DOWN_CONNECT: (
        "Model sunucusuna ulaşılamadı (http://fake-model.invalid/v1): bağlantı reddedildi — "
        "adres/port yanlış ya da sunucu kapalı"
    ),
    fake_model.DOWN_UNAUTHORIZED: "Sunucu HTTP 401 döndürdü (API anahtarı eksik veya geçersiz)",
}


class SourceClient:
    """The fake core behind the source's ``LLMClient`` contract."""

    def __init__(self, core: fake_model.FakeAnalyst) -> None:
        self.core = core
        self.last_error = ""

    @property
    def available(self) -> bool:
        return self.core.available

    @property
    def model(self) -> str:
        return self.core.model

    def health(self) -> str:
        return _HEALTH_ERRORS[self.core.health()]

    def chat_json(
        self, system: str, user: str, schema: Mapping[str, Any], *, max_tokens: int = 1024
    ) -> dict[str, Any] | None:
        reply, failure = self.core.reply(system, user, schema, max_tokens)
        if failure:
            self.last_error = _CHAT_ERRORS[failure]
        return reply


class SourceSide:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp

    def parse_dictionary(self, data: bytes) -> tuple[Any, dict[str, Any]]:
        workbook = self.tmp / "sozluk.xlsx"
        workbook.write_bytes(data)
        store = dictionary_store.from_workbook(workbook)
        path = self.tmp / "dictionary.jsonl"
        dictionary_store.save(store, path)
        d = dictionary_store.load_dictionary(path)
        meta = store.meta
        parsed = dictionary_dump(
            meta["version"], meta["digest"], store.objects, store.columns, store.warnings, d
        )
        return d, parsed

    def empty_dictionary(self) -> Any:
        return dictionary_store.empty(Path("dictionary.jsonl"))

    def word_lists(self, terms: Sequence[Path], stopwords: Path) -> tuple[list[Any], Any]:
        groups = [g for path in terms for g in load_term_dictionary(path)]
        return groups, load_stopword_file(stopwords)

    def engine(
        self, dictionary: Any, overrides: Mapping[str, Any], groups: list[Any], stop: Any, llm: Any
    ) -> Any:
        settings = Settings()
        for key, value in SAMPLING.items():
            if getattr(settings.llm, key) != value and key != "model":
                raise ValueError(f"kaynak model ayarı beklenenden farklı: {key}")
        settings.llm.model = SAMPLING["model"]
        apply_overrides(settings, overrides)
        return Engine(dictionary, settings, Resources(list(groups), stop), llm=llm)

    def client(self, core: fake_model.FakeAnalyst) -> Any:
        return SourceClient(core)

    def encode(self, result: Any) -> dict[str, Any]:
        return answer_cache.encode(result)

    def fingerprint(self, engine: Any, top_n: int) -> str:
        return engine.cache_fingerprint(top_n)

    def prompts_digest(self) -> str:
        return answer_cache.prompts_digest()

    def report(self, result: Any) -> bytes:
        path = self.tmp / "rapor.xlsx"
        excel.write_ask_report(result, path)
        return path.read_bytes()

    def slugify(self, query: str) -> str:
        return excel.slugify(query)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)  # the source logs names it drops; nothing to see here
    with tempfile.TemporaryDirectory(prefix="parity-source-") as tmp:
        raise SystemExit(main(SourceSide(Path(tmp))))
