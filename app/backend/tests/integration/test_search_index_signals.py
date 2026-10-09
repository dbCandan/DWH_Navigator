"""Search index signals (data-dictionary 009-search-settings Gözlemlenebilirlik).

Builds and changes by trigger and outcome, the ready gauge, the ``search_change.apply`` span with
its ``search_index.build`` child, and no setting value, list content or user in any signal.
"""

import pytest

from tests.fakes.telemetry import TelemetryCapture
from tests.integration.conftest import RecordingHandler
from tests.integration.data_dictionary import DataDictionary, error, started_index

pytestmark = pytest.mark.integration

BUILDS = "dwhnavigator_search_index_builds_total"
CHANGES = "dwhnavigator_search_changes_total"


async def test_builds_changes_and_the_ready_gauge(
    dd: DataDictionary, telemetry_capture: TelemetryCapture, recorded_logs: RecordingHandler
) -> None:
    marker = "GIZLITERIM5"
    dd.use_index(await started_index(queue_timeout=0.2))
    assert (await dd.patch_settings({"analyst.shortlist": 9})).status_code == 200
    assert (await dd.patch_settings({"analyst.shortlist": 9})).json()["changed"] == []
    group = {"term": marker, "equivalents": [f"{marker}x"], "domain": marker, "note": marker}
    assert (await dd.put_list("terms", [group])).status_code == 200
    assert (await dd.request("POST", "/search-index/rebuilds")).status_code == 200
    await dd.index._lock.acquire()
    try:
        assert error(await dd.put_list("stopwords", [{"word": marker}])) == (
            503,
            "search_change_busy",
        )
    finally:
        dd.index._lock.release()

    capture = telemetry_capture
    assert capture.value(BUILDS, trigger="startup", outcome="ok") == 1
    assert capture.value(BUILDS, trigger="settings", outcome="ok") == 1
    assert capture.value(BUILDS, trigger="terms", outcome="ok") == 1
    assert capture.value(BUILDS, trigger="manual", outcome="ok") == 1
    assert capture.value(CHANGES, trigger="settings", outcome="applied") == 1
    assert capture.value(CHANGES, trigger="settings", outcome="unchanged") == 1
    assert capture.value(CHANGES, trigger="terms", outcome="applied") == 1
    assert capture.value(CHANGES, trigger="stopwords", outcome="busy") == 1
    assert capture.value("dwhnavigator_search_index_ready") == 1
    durations = capture.points("dwhnavigator_search_index_build_duration_seconds")
    assert {labels["trigger"] for labels, _ in durations} == {
        "startup",
        "settings",
        "terms",
        "manual",
    }
    applies = capture.spans("search_change.apply")
    builds = capture.spans("search_index.build")
    assert {(s.attributes or {}).get("dwhnavigator.search.outcome") for s in applies} == {
        "applied",
        "unchanged",
    }
    child = next(
        b for b in builds if (b.attributes or {})["dwhnavigator.search.trigger"] == "terms"
    )
    parent = next(
        a for a in applies if (a.attributes or {})["dwhnavigator.search.trigger"] == "terms"
    )
    assert child.parent is not None and child.parent.span_id == parent.context.span_id
    assert marker not in capture.everything() and marker not in recorded_logs.rendered()
    assert dd.manager.public_id not in capture.everything()
    build_events = recorded_logs.events("search_index.build")
    assert {e["trigger"] for e in build_events} >= {"settings", "terms", "manual"}
    assert all(set(e) <= {"event", "trigger", "outcome", "duration_ms", "columns", "objects",
                          "error_type"} for e in build_events)  # fmt: skip
    assert recorded_logs.events("search_change.busy") == [
        {"event": "search_change.busy", "trigger": "stopwords"}
    ]
    saved = recorded_logs.events("vocabulary.saved")
    assert saved[0]["list"] == "terms" and saved[0]["items"] == 1 and saved[0]["changed"] is True
