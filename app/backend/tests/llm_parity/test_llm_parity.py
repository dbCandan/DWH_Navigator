"""Byte-for-byte parity of the model adapter with the source client 76e21a3 (Acceptance 2).

Requirement 6, 7, 8 and 13: for every scenario the fake server receives exactly the request bodies
the source client sent (adaptation and repair resends included), the returned JSON objects are
equal, and each failure is its Requirement 13 class. The source side is recorded in the snapshot
by ``tests.llm_parity.run_source``; with ``DWHNAVIGATOR_PARITY_SOURCE_DIR`` naming an export of the
source at that commit, the source is also run again here and must reproduce the snapshot. The only
target difference is the declared ``chat_template_kwargs`` field of Requirement 7, rule 3
(``Scenario.thinking_off_from``); it is added to the source bytes here, never to the snapshot.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.domain.llm import (
    LlmChatRequest,
    LlmConnection,
    LlmOutcome,
    LlmPurpose,
    short_reason,
)
from app.infrastructure.llm.openai_adapter import OpenAICompatibleAdapter
from tests.llm_parity.scenarios import SCENARIOS, SOURCE_COMMIT, Scenario
from tests.llm_parity.stdlib_server import ScriptedServer

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]
SNAPSHOT = Path(__file__).with_name("snapshots") / "source-76e21a3.json"


def _snapshot() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return data


def _with_thinking_off(body: str) -> str:
    """The source body with ``chat_template_kwargs`` in the place of the dropped effort."""

    fields = json.loads(body)
    # json.dumps defaults write the source's bytes back unchanged (Decision 6).
    assert json.dumps(fields) == body
    assert "reasoning_effort" not in fields and "chat_template_kwargs" not in fields
    written: dict[str, Any] = {}
    for name, value in fields.items():
        written[name] = value
        if name == "max_tokens":
            written["chat_template_kwargs"] = {"enable_thinking": False}
    return json.dumps(written)


def target_bodies(scenario: Scenario, source_bodies: list[str]) -> list[str]:
    """What the target must send: the source's bodies plus the declared difference only."""

    start = scenario.thinking_off_from
    if start is None:
        return list(source_bodies)
    return [
        _with_thinking_off(body) if index >= start else body
        for index, body in enumerate(source_bodies)
    ]


def test_the_declared_difference_follows_a_refused_none_effort_only() -> None:
    for scenario in SCENARIOS:
        source = _snapshot()["scenarios"][scenario.name]["bodies"]
        if scenario.thinking_off_from is None:
            continue
        assert scenario.reasoning_effort == "none"
        start = scenario.thinking_off_from
        # The first request is never changed, and the change starts where the effort was dropped.
        assert start >= 1
        assert '"reasoning_effort": "none"' in source[start - 1]
        assert all('"reasoning_effort"' not in body for body in source[start:])


def test_the_snapshot_is_the_source_commit_and_covers_every_scenario() -> None:
    data = _snapshot()
    assert data["source_commit"] == SOURCE_COMMIT
    assert set(data["scenarios"]) == {scenario.name for scenario in SCENARIOS}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[scenario.name for scenario in SCENARIOS])
async def test_the_adapter_sends_the_source_bytes(scenario: Scenario) -> None:
    source = _snapshot()["scenarios"][scenario.name]
    server = ScriptedServer(scenario.answers)
    outcomes: list[str] = []
    values: list[Any] = []
    try:
        adapter = OpenAICompatibleAdapter(ca_bundle="", max_concurrent_calls=2)
        connection = LlmConnection(
            endpoint=server.url,
            chat_model=scenario.model,
            temperature=scenario.temperature,
            timeout_seconds=30,
            reasoning_effort=scenario.reasoning_effort,
            seed=scenario.seed,
            api_key=scenario.api_key or None,
            public_id=f"parite-{scenario.name}",
        )
        for call in scenario.calls:
            result = await adapter.chat(
                connection,
                LlmChatRequest(
                    system=call.system,
                    user=call.user,
                    schema=call.schema,
                    max_tokens=call.max_tokens,
                    purpose=LlmPurpose.ANALYSIS,
                ),
            )
            outcomes.append(result.outcome.value)
            values.append(result.value)
            if not result.ok:
                # The class's fixed text: no server text, address or exception reaches it.
                reason = short_reason(result.outcome, result.http_status, probe=False)
                assert "error" not in reason and "127.0.0.1" not in reason
    finally:
        server.close()

    assert [body.decode("ascii") for body in server.bodies] == target_bodies(
        scenario, source["bodies"]
    )
    assert values == source["values"]
    assert outcomes == list(scenario.expected)
    # The source failed exactly where the target failed.
    assert [error != "" for error in source["errors"]] == [
        outcome != LlmOutcome.OK.value for outcome in outcomes
    ]


def test_the_source_reproduces_the_snapshot_when_its_copy_is_given() -> None:
    copy = os.environ.get("DWHNAVIGATOR_PARITY_SOURCE_DIR")
    if not copy:
        pytest.skip("set DWHNAVIGATOR_PARITY_SOURCE_DIR to an export of the source at 76e21a3")
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "tests.llm_parity.run_source",
            "--source",
            copy,
            "--check",
            str(SNAPSHOT),
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
