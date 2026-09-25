"""End-to-end: M1 acceptance on the golden set, report and CLI (needs the real dictionary)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from openpyxl import load_workbook

from vsa.config import Settings
from vsa.evaluation import evaluate, load_golden
from vsa.models import Verdict
from vsa.pipeline import Engine
from vsa.report.excel import report_path, slugify, write_ask_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def engine() -> Engine:
    from .conftest import REAL_DICTIONARY

    if not REAL_DICTIONARY.exists():
        pytest.skip("Gerçek sözlük yok (data/ gitignore'da)")
    logging.disable(logging.WARNING)
    settings = Settings()
    settings.dictionary.path = str(REAL_DICTIONARY)
    return Engine.from_dictionary_file(settings)


def test_m1_acceptance(engine: Engine) -> None:
    """HANDOVER §17 M1: expected object in the top 5 for every golden ask item;
    no trap violations; every negative item answered BULUNAMADI (ADR-006)."""
    report = evaluate(
        engine,
        load_golden(ROOT / "tests" / "golden_set.yaml"),
        load_golden(ROOT / "tests" / "negative_set.yaml"),
    )
    asks = report.group("ask")
    assert asks
    misses = [i.id for i in asks if not i.rank or i.rank > 5]
    assert misses == [], misses
    assert report.trap_violations == 0
    assert report.false_answer_rate == 0.0


def test_ask_report(engine: Engine, tmp_path: Path) -> None:
    result = engine.analyze("Kredi kartı limit doluluk oranı", top_n=3)
    assert result.verdict is not Verdict.NOT_FOUND
    assert 0 < len(result.objects) <= 3
    assert result.dropped_by_validation == 0
    keys = engine.column_keys
    assert all(h.col.key in keys for m in result.objects for h in m.columns)

    path = write_ask_report(result, report_path(tmp_path, "ask", result.query))
    wb = load_workbook(path)
    assert wb.sheetnames == ["Özet", "Öneriler", "Alan Detayları", "Notlar ve Öneriler"]
    ws = wb["Öneriler"]
    assert ws["A1"].value == "Sıra"
    assert ws["A1"].font.name == "Arial"
    assert ws["I2"].number_format == "0%"
    assert ws.freeze_panes == "A2"
    assert "sürüm" in str(wb["Özet"]["B3"].value)


def test_irrelevant_query_does_not_crash(engine: Engine) -> None:
    result = engine.analyze("zzzz qqqq")
    assert result.verdict is Verdict.NOT_FOUND
    assert result.objects == []


def test_slug() -> None:
    assert slugify("Kredi kartı limit doluluk oranı?") == "kredi_karti_limit_doluluk_orani"


def test_m5_batch_acceptance(engine: Engine) -> None:
    """M5 regression guard on the Ek A.3 target-table request (values as of 2026-09-26)."""
    report = evaluate(engine, load_golden(ROOT / "tests" / "golden_set.yaml"))
    assert report.recall(3, "batch") >= 0.9
    assert report.status_accuracy() >= 0.9


def test_batch_report(engine: Engine, tmp_path: Path) -> None:
    from vsa.batch import BatchAnalyzer
    from vsa.models import FieldStatus, RequestField
    from vsa.report.excel import write_batch_report

    fields = [
        RequestField(1, "CustomerId", "CustomerId", "Müşteri numarası"),
        RequestField(2, "Period", "Period", "Ay, yıl örn: 202604"),
        RequestField(
            3, "Farklı Banka Sayısı", "DistinctBankCount", "Gönderilen farklı banka sayısı"
        ),
        RequestField(4, "Uzay Gemisi Yakıtı", "SpaceshipFuel", "Roket yakıt seviyesi"),
    ]
    result = BatchAnalyzer(engine).analyze(fields, "test")
    by_name = {r.field.en: r for r in result.fields}
    assert by_name["Period"].status is FieldStatus.READY
    assert by_name["DistinctBankCount"].status is FieldStatus.DERIVE
    best = by_name["DistinctBankCount"].best
    assert best is not None and best.derivation.startswith("COUNT(DISTINCT")
    keys = engine.column_keys
    assert all(
        h.col.key in keys for r in result.fields for c in r.candidates for h in c.match.columns
    )

    path = write_batch_report(result, tmp_path / "b.xlsx")
    wb = load_workbook(path)
    assert wb.sheetnames == ["Özet", "Alan Eşleştirme", "Alan Detayları", "Notlar ve Öneriler"]
    assert wb["Alan Eşleştirme"]["E1"].value == "Durum"
