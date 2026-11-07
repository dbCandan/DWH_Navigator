"""The model connection settings (data-dictionary 003-llm-connection Requirement 1)."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.llm_connections import shared_adapter
from tests.fakes.llm_server import write_pki

pytestmark = pytest.mark.unit


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


def test_defaults_use_the_system_trust_store_and_five_slots() -> None:
    # Decision 11: four parallel analyses (question-analysis Decision 27) and a connection test.
    settings = _settings()
    assert settings.llm_ca_bundle == ""
    assert settings.llm_max_concurrent_calls == 5
    assert settings.analysis_concurrency == 4
    assert settings.llm_max_concurrent_calls > settings.analysis_concurrency


@pytest.mark.parametrize("value", [0, 9, -1])
def test_the_analysis_concurrency_is_one_to_eight(value: int) -> None:
    with pytest.raises(ValidationError):
        _settings(analysis_concurrency=value)
    assert _settings(analysis_concurrency=8).analysis_concurrency == 8


@pytest.mark.parametrize("value", [0, 9, -1])
def test_the_slot_limit_is_one_to_eight(value: int) -> None:
    with pytest.raises(ValidationError):
        _settings(llm_max_concurrent_calls=value)
    assert _settings(llm_max_concurrent_calls=8).llm_max_concurrent_calls == 8


def test_an_unreadable_trust_store_stops_start_up(tmp_path: Path) -> None:
    missing = tmp_path / "yok.pem"
    with pytest.raises(ValidationError) as missing_error:
        _settings(llm_ca_bundle=str(missing))
    assert str(missing) not in str(missing_error.value)
    garbage = tmp_path / "bozuk.pem"
    garbage.write_text("sertifika değil", encoding="utf-8")
    with pytest.raises(ValidationError):
        _settings(llm_ca_bundle=str(garbage))


def test_a_certificate_file_is_accepted(tmp_path: Path) -> None:
    pki = write_pki(tmp_path / "pki")
    assert _settings(llm_ca_bundle=f" {pki.ca_path} ").llm_ca_bundle == str(pki.ca_path)


def test_the_process_shares_one_adapter_per_configuration() -> None:
    settings = _settings()
    assert shared_adapter(settings) is shared_adapter(_settings())
    assert shared_adapter(settings) is not shared_adapter(_settings(llm_max_concurrent_calls=3))
