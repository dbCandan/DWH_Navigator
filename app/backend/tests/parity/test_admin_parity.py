"""Settings schema and word lists against the source 76e21a3 (009 and 002 fark testi).

The target's settings schema is the source's ``settings_schema.SECTIONS`` field for field, apart
from the five removed file and folder fields, the two ¹ texts of search-settings Requirement
1 and the target-only step 1 token limit (``ADDED``); the defaults are the source's. ``check_terms`` / ``check_stopwords`` give the source's result
or message for every case, the word list workbooks read and write the same, and the engine reads
the seed lists as the source does: 45 groups and 124 forms (vocabulary-management Acceptance 1).
The source side is the committed snapshot; ``python -m tests.parity.harness --verify-snapshot``
rebuilds it from the source copy.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.parity import admin, harness

pytestmark = pytest.mark.unit

REMOVED = {
    "dictionary.store",
    "expansion.term_dictionary",
    "expansion.stopwords",
    "report.out_dir",
    "index.dir",
}
# Target only: step 1 of the analyst had a fixed 2500-token reply limit in the source, which a
# thinking model filled before its JSON; the target makes it a setting.
ADDED = {
    "analyst.shortlist_max_tokens": {
        "key": "analyst.shortlist_max_tokens",
        "label": "Aday seçimi için en fazla token",
        "help": "1. adımda modelin yazabileceği en uzun cevap (aday tablo listesi).",
        "type": "int",
        "effect": "immediate",
        "format": None,
        "min": 1000,
        "max": 32000,
        "step": 500,
        "advanced": True,
    }
}
ADDED_DEFAULTS = {"analyst.shortlist_max_tokens": 8000}
CHANGED_HELP = {
    "expansion.enabled": "Katılım bankacılığı terimleri ve kısaltmalar (Yönetim → Kelimeler)."
}
CHANGED_INTRO = {
    "ranking": "Kural puanı (beş parça) modele ipucu olur, cevap yazmaz; değiştirmeden önce ve "
    "sonra altın setle ölçün."
}
EFFECTS = {"anında": "immediate", "indeks": "reindex"}


@pytest.fixture(scope="module")
def sides() -> tuple[dict[str, Any], dict[str, Any]]:
    source = json.loads((harness.SNAPSHOT / "admin.json").read_text(encoding="utf-8"))
    target = json.loads(json.dumps(admin.collect("target"), ensure_ascii=False))
    return source, target


def _fields(sections: list[dict[str, Any]]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    return {f["key"]: (s, f) for s in sections for f in s["fields"]}


def test_the_settings_schema_is_the_sources(sides: tuple[dict[str, Any], dict[str, Any]]) -> None:
    source, target = sides
    theirs = _fields(source["settings"]["sections"])
    ours = _fields(target["settings"]["sections"])
    assert set(theirs) - set(ours) == REMOVED and set(ours) - set(theirs) == set(ADDED)
    # same order
    assert [k for k in ours if k not in ADDED] == [k for k in theirs if k not in REMOVED]
    for key, (section, field) in ours.items():
        if key in ADDED:
            assert field == ADDED[key] and section["id"] == "analyst", key
            continue
        their_section, their_field = theirs[key]
        expected = {
            "key": key,
            "label": their_field["label"],
            "help": CHANGED_HELP.get(key, their_field["help"]),
            "type": their_field["type"],
            "effect": EFFECTS[their_field["effect"]],
            "format": their_field.get("format"),
            "min": their_field.get("min"),
            "max": their_field.get("max"),
            "step": their_field.get("step"),
            "advanced": their_field.get("advanced", False),
        }
        assert field == expected, key
        assert {k: section[k] for k in ("id", "page", "title")} == {
            k: their_section[k] for k in ("id", "page", "title")
        }
        assert section["intro"] == CHANGED_INTRO.get(section["id"], their_section["intro"])
        assert section["advanced"] == their_section.get("advanced", False)
    defaults = source["settings"]["defaults"]
    assert target["settings"]["defaults"] == {k: {**defaults, **ADDED_DEFAULTS}[k] for k in ours}


def test_word_list_checks_and_workbooks_are_the_sources(
    sides: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    source, target = sides
    assert target["checks"] == source["checks"]
    assert target["workbooks"] == source["workbooks"]
    assert target["engine_reading"] == source["engine_reading"]
    assert len(target["engine_reading"]["term_groups"]) == 45
    assert len(target["engine_reading"]["stopword_forms"]) == 124


def test_the_cases_cover_every_message(sides: tuple[dict[str, Any], dict[str, Any]]) -> None:
    source, _target = sides
    errors = {
        case.get("error", "").split(":")[-1].strip()
        for group in ("terms", "stopwords")
        for case in source["checks"][group]
    }
    assert {"terim boş", "en az bir eşdeğer gerekli", "durak kelime tek kelime olmalı"} <= errors
    assert any("iki kez var" in e for e in errors) and "En fazla 5000 kayıt" in errors
    assert len(admin.TERM_CASES) == len(source["checks"]["terms"])
