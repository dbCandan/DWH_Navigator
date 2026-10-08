"""The constant parity test's dump (question-analysis Requirement 1, "sabit fark testi").

    python -B -m tests.parity.constants source   # with the source copy's src on the path
    python -B -m tests.parity.constants target

Prints, keyed by the source module name, every upper-case constant of each ported module and
the members of its enumerations, the measured settings defaults and the prompt digest.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
from typing import Any

from tests.parity.dump import constant, module_constants

# Source module -> the target module it was ported to.
MODULES = {
    "vsa.models": "app.domain.analysis",
    "vsa.text.normalize": "app.services.analysis.text.normalize",
    "vsa.expansion.query_expander": "app.services.analysis.expansion.query_expander",
    "vsa.features": "app.services.analysis.features",
    "vsa.index.bm25": "app.services.analysis.index.bm25",
    "vsa.scoring.rules": "app.services.analysis.scoring.rules",
    "vsa.scoring.aggregate": "app.services.analysis.scoring.aggregate",
    "vsa.scoring.combine": "app.services.analysis.scoring.combine",
    "vsa.scoring.topic": "app.services.analysis.scoring.topic",
    "vsa.scoring.explain": "app.services.analysis.scoring.explain",
    "vsa.validate": "app.services.analysis.validate",
    "vsa.llm.analyst": "app.services.analysis.llm.analyst",
    "vsa.llm.analyst_prompts": "app.services.analysis.llm.analyst_prompts",
    "vsa.answer_cache": "app.services.analysis.answer_cache",
    "vsa.cancel": "app.services.analysis.cancel",
    "vsa.trace": "app.services.analysis.trace",
    "vsa.pipeline": "app.services.analysis.pipeline",
    "vsa.report.excel": "app.services.analysis.report.excel",
    "vsa.loader": "app.services.analysis.loader",
    "vsa.dictionary_store": "app.services.analysis.dictionary_workbook",
    "vsa.feedback": "app.services.analysis.feedback",
}
# Source module -> the application module that now owns part of its constants: the case folding
# tables of the source's normalization are the application's one Turkish folding helper.
SHARED = {"vsa.text.normalize": "app.domain.turkish_text"}
# Settings sections and fields the target keeps: the rest are file paths and the model
# connection, which the target reads from PostgreSQL and the llm-connection PRD.
SETTINGS_SECTIONS = ("search", "expansion", "scoring", "analyst", "cache")
SOURCE_ONLY_SETTINGS = {"expansion": ("term_dictionary", "stopwords")}


def settings_defaults(settings: Any) -> dict[str, Any]:
    raw = dataclasses.asdict(settings)
    out = {name: raw[name] for name in SETTINGS_SECTIONS}
    for section, names in SOURCE_ONLY_SETTINGS.items():
        for name in names:
            out[section].pop(name, None)
    return out


def collect(side: str) -> dict[str, Any]:
    modules = {
        source: importlib.import_module(source if side == "source" else target)
        for source, target in MODULES.items()
    }
    config = importlib.import_module(
        "vsa.config" if side == "source" else "app.services.analysis.config"
    )
    constants = {name: module_constants(module) for name, module in modules.items()}
    if side == "target":
        for source, owner in SHARED.items():
            constants[source] |= module_constants(importlib.import_module(owner))
    return {
        "modules": constants,
        "settings": constant(settings_defaults(config.Settings())),
        "prompts_digest": modules["vsa.answer_cache"].prompts_digest(),
    }


if __name__ == "__main__":
    json.dump(collect(sys.argv[1]), sys.stdout, ensure_ascii=False, sort_keys=True)
