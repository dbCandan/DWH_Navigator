"""Logs, metrics and traces of analysis jobs carry no content (data-dictionary/PRDs/
004-question-analysis Gözlemlenebilirlik, Acceptance 5; 008-analysis-records Requirement 4).

Marker strings in the question and in the model's reply must reach the analysis record (product
data) and never the log, a metric label or a span attribute; the record never carries the model
server's address or reply text outside the checked answer.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator

import pytest

from tests.fakes.telemetry import TelemetryCapture
from tests.integration.analysis import Qa, qa_harness, record
from tests.integration.conftest import RecordingHandler
from tests.integration.data_dictionary import DataDictionary

pytestmark = pytest.mark.integration

QUESTION_MARKER = "QZXSORUISARETI"
REPLY_MARKER = "QZXMODELISARETI"


@pytest.fixture
async def qa(dd: DataDictionary) -> AsyncIterator[Qa]:
    async for harness in qa_harness(dd):
        yield harness


@pytest.fixture
def analysis_logs(recorded_logs: RecordingHandler) -> Iterator[RecordingHandler]:
    loggers = [logging.getLogger(name) for name in ("app.analysis", "app.llm")]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.INFO)
    try:
        yield recorded_logs
    finally:
        for logger, level in zip(loggers, levels, strict=True):
            logger.setLevel(level)


async def test_no_content_reaches_logs_metrics_or_traces(
    qa: Qa, analysis_logs: RecordingHandler, telemetry_capture: TelemetryCapture
) -> None:
    qa.model.reply_marker = REPLY_MARKER
    analysis_id = await qa.started(f"kart limit doluluk {QUESTION_MARKER}")
    done = await qa.finished(analysis_id)
    assert done["flow"] == "analyst"
    report = await qa.request("GET", f"/analyses/{analysis_id}/report")
    assert report.status_code == 200
    cancelled = await qa.started(f"mevduat {QUESTION_MARKER}", fresh=True)
    await qa.request("POST", f"/analyses/{cancelled}/cancel")
    await qa.finished(cancelled)
    await asyncio.sleep(0.1)

    logs = analysis_logs.rendered()
    signals = telemetry_capture.everything()
    for marker in (QUESTION_MARKER, REPLY_MARKER, "127.0.0.1", "kart limit"):
        assert marker not in logs, marker
        assert marker not in signals, marker
    row = await record(analysis_id)
    assert QUESTION_MARKER in row["query"] and QUESTION_MARKER in row["search_key"].upper()
    assert REPLY_MARKER in json.dumps(row["result"], ensure_ascii=False)
    assert REPLY_MARKER not in json.dumps(row["steps"], ensure_ascii=False)
    assert "127.0.0.1" not in json.dumps(row["steps"]) + json.dumps(row["result"])

    events = {name: analysis_logs.events(name) for name in (
        "analysis.accepted", "analysis.started", "analysis.finished",
        "analysis.report_generated", "llm.call",
    )}  # fmt: skip
    assert len(events["analysis.accepted"]) == 2
    finished = {e["analysis_id"]: e for e in events["analysis.finished"]}
    assert finished[analysis_id]["outcome"] == "analyst"
    assert finished[analysis_id]["llm_calls"] == 2
    assert finished[cancelled]["outcome"] == "cancelled"
    assert finished[cancelled]["error_code"] == "cancelled"
    assert events["analysis.report_generated"][0]["size_bytes"] > 0
    assert {e["analysis_public_id"] for e in events["llm.call"]} >= {analysis_id}

    capture = telemetry_capture
    assert capture.value("dwhnavigator_analyses_started_total", origin="question") >= 1
    assert (
        capture.value("dwhnavigator_analyses_finished_total", origin="question", outcome="analyst")
        == 1
    )
    assert (
        capture.value(
            "dwhnavigator_analyses_finished_total", origin="question", outcome="cancelled"
        )
        == 1
    )
    assert capture.value("dwhnavigator_saved_answer_writes_total", result="stored") == 1
    assert capture.value("dwhnavigator_saved_answer_lookups_total", result="miss") >= 1
    assert capture.value("dwhnavigator_analysis_reports_total", result="ok") == 1
    steps = {labels["step"] for labels, _ in capture.points(
        "dwhnavigator_analysis_step_duration_seconds"
    )}  # fmt: skip
    assert {"queue", "model_check", "rule_hints", "shortlist", "analyst_report"} <= steps
    runs = capture.spans("analysis.run")
    assert {s.attributes["dwhnavigator.analysis.outcome"] for s in runs} >= {
        "analyst", "cancelled"
    }  # fmt: skip
    chats = capture.spans("llm chat")
    step_ids = {s.context.span_id for s in capture.spans("shortlist")}
    assert any(c.parent is not None and c.parent.span_id in step_ids for c in chats)
