"""The settings schema, its checks and the fingerprint (search-settings Requirement 1-4, 7, 8).

The source comparison of every field is in tests/parity/test_admin_parity.py.
"""

import math
from typing import Any

import pytest

from app.services.analysis.config import Settings
from app.services.analysis.llm.port import ModelSampling
from app.services.analysis.pipeline import Engine, Resources
from app.services.search_settings_schema import (
    CACHE_KEYS,
    FIELDS,
    SECTIONS,
    SearchSettingsRejected,
    SettingEffect,
    check_values,
    defaults,
    effective_values,
    engine_settings,
    needs_reindex,
    section_dicts,
    settings_digest,
    values_of,
)
from tests.unit.analysis.workbooks import (
    SAMPLE_OBJECTS,
    SAMPLE_ROWS,
    import_workbook,
    xlsx_bytes,
)

pytestmark = pytest.mark.unit

SAMPLING = ModelSampling("model", 0.0, "none", 42)


def _rejected(values: dict[str, Any]) -> tuple[str, str]:
    with pytest.raises(SearchSettingsRejected) as refused:
        check_values(values)
    return refused.value.code, refused.value.message


def test_five_sections_and_twenty_four_fields_on_two_pages() -> None:
    assert [(s.id, s.page, s.advanced) for s in SECTIONS] == [
        ("analyst", "search", False),
        ("terms", "search", False),
        ("ranking", "search", True),
        ("words", "search", True),
        ("cache", "data", False),
    ]
    assert len(FIELDS) == 24
    assert not any(key.startswith(("llm.", "dictionary.", "report.", "index.")) for key in FIELDS)
    assert "expansion.term_dictionary" not in FIELDS and "expansion.stopwords" not in FIELDS
    assert FIELDS["expansion.enabled"].help == (
        "Katılım bankacılığı terimleri ve kısaltmalar (Yönetim → Kelimeler)."
    )
    assert SECTIONS[2].intro.endswith("değiştirmeden önce ve sonra altın setle ölçün.")
    reindex = [k for k, f in FIELDS.items() if f.effect is SettingEffect.REINDEX]
    assert reindex == [
        "search.field_weights.name",
        "search.field_weights.synonyms",
        "search.field_weights.description",
        "search.field_weights.object",
        "search.bm25.k1",
        "search.bm25.b",
    ]
    api = section_dicts()
    assert api[0]["fields"][2] == {
        "key": "analyst.min_confidence",
        "label": "Gösterilecek en düşük model güveni",
        "help": "Modelin bundan az emin olduğu tablolar önerilmez (“bulunamadı” geçerli cevap).",
        "type": "float",
        "effect": "immediate",
        "format": "pct",
        "min": 0,
        "max": 1,
        "step": 0.05,
        "advanced": False,
    }


def test_defaults_are_the_engines_measured_settings() -> None:
    values = defaults()
    assert values == values_of(Settings())
    assert values["analyst.shortlist"] == 14 and values["search.bm25.k1"] == 1.2
    assert values["search.field_weights.name"] == 3.0 and values["cache.max_age_days"] == 30


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"expansion.enabled": 1}, "Kurumsal terim sözlüğünü kullan: açık/kapalı olmalı"),
        ({"expansion.enabled": "true"}, "Kurumsal terim sözlüğünü kullan: açık/kapalı olmalı"),
        ({"analyst.shortlist": "5"}, "Kolonları okunacak aday tablo sayısı: sayı olmalı"),
        ({"analyst.shortlist": True}, "Kolonları okunacak aday tablo sayısı: sayı olmalı"),
        ({"analyst.shortlist": None}, "Kolonları okunacak aday tablo sayısı: sayı olmalı"),
        ({"search.bm25.b": math.nan}, "BM25 b: sayı olmalı"),
        ({"analyst.shortlist": 5.5}, "Kolonları okunacak aday tablo sayısı: tam sayı olmalı"),
        (
            {"analyst.shortlist": 31},
            "Kolonları okunacak aday tablo sayısı: 3 ile 30 arasında olmalı",
        ),
        ({"search.bm25.k1": 0.05}, "BM25 k1: 0.1 ile 3 arasında olmalı"),
    ],
)
def test_a_wrong_value_is_refused_with_the_sources_message(
    values: dict[str, Any], message: str
) -> None:
    assert _rejected(values) == ("search_setting_invalid", message)


def test_unknown_keys_and_every_error_are_joined() -> None:
    code, message = _rejected(
        {"llm.endpoint": "http://x", "analyst.shortlist": 2, "nope": 1, "cache.enabled": True}
    )
    assert code == "search_setting_unknown"
    assert message == (
        "Bilinmeyen ayar: llm.endpoint; Kolonları okunacak aday tablo sayısı: 3 ile 30 arasında "
        "olmalı; Bilinmeyen ayar: nope"
    )


def test_checked_values_have_the_fields_type() -> None:
    checked = check_values(
        {"analyst.shortlist": 5.0, "expansion.weight": 1, "cache.meaning": False}
    )
    assert checked == {"analyst.shortlist": 5, "expansion.weight": 1.0, "cache.meaning": False}
    assert isinstance(checked["analyst.shortlist"], int)
    assert isinstance(checked["expansion.weight"], float)
    assert check_values({}) == {}


def test_effective_values_and_engine_settings() -> None:
    values = effective_values({"search.field_weights.object": 2.5, "analyst.shortlist": 9})
    settings = engine_settings(values)
    assert settings.search.field_weights["object"] == 2.5
    assert settings.analyst.shortlist == 9
    assert values_of(settings) == values
    # The ten constants of Requirement 8 keep their measured values.
    assert settings.analyst.confusables == 6 and settings.scoring.rule_only_factor == 0.8
    assert settings_digest(values) != settings_digest(defaults())
    assert settings_digest(effective_values({})) == settings_digest(defaults())


def test_only_the_word_index_fields_need_a_reindex() -> None:
    assert needs_reindex(["search.bm25.k1"]) and needs_reindex(["cache.enabled", "search.bm25.b"])
    assert not needs_reindex(["analyst.shortlist", "cache.enabled", "expansion.weight"])
    assert CACHE_KEYS == {"cache.enabled", "cache.meaning", "cache.max_age_days"}


def test_the_fingerprint_leaves_the_cache_settings_out_and_returns_with_a_value() -> None:
    dictionary = import_workbook(xlsx_bytes({"Objeler": SAMPLE_OBJECTS, "Kolonlar": SAMPLE_ROWS}))

    def fingerprint(**changes: Any) -> str:
        settings = engine_settings(effective_values(changes))
        return Engine(dictionary, settings, Resources()).cache_fingerprint(
            "kart limit", 5, SAMPLING
        )

    base = fingerprint()
    assert fingerprint(**{"cache.enabled": False, "cache.meaning": False}) == base
    assert fingerprint(**{"cache.max_age_days": 0}) == base
    assert fingerprint(**{"analyst.shortlist": 9}) != base
    assert fingerprint(**{"search.bm25.k1": 1.5}) != base
    assert fingerprint(**{"analyst.shortlist": 14}) == base  # back to the default value
