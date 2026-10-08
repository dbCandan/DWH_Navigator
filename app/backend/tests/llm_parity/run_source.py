"""The source side: the source client ``OpenAICompatibleClient`` of commit 76e21a3.

    python -B -m tests.llm_parity.run_source --source <copy> --write <snapshot>
    python -B -m tests.llm_parity.run_source --source <copy> --check <snapshot>

``<copy>`` is an export of the source repository at that commit (``git archive 76e21a3``); every
imported source file must have its blob id at the commit, or the run stops. Only the standard
library and the source package run here; the source is never copied into this repository. The
snapshot keeps, per scenario, the request bodies the server received, the returned objects and
the source's own error texts.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from tests.llm_parity.scenarios import SCENARIOS, SOURCE_BLOBS, SOURCE_COMMIT
from tests.llm_parity.stdlib_server import ScriptedServer


def _blob_id(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def verify_source(source: Path) -> None:
    for relative, expected in SOURCE_BLOBS.items():
        actual = _blob_id(source / relative)
        if actual != expected:
            raise SystemExit(f"kaynak dosyası {SOURCE_COMMIT[:7]} ile aynı değil: {relative}")


def run(source: Path) -> dict[str, Any]:
    verify_source(source)
    # The source opener reads proxy settings when it is imported; the fake server is local.
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(name, None)
    os.environ["no_proxy"] = "*"
    sys.path.insert(0, str(source / "src"))
    from vsa.llm.client import OpenAICompatibleClient

    results: dict[str, Any] = {}
    for scenario in SCENARIOS:
        server = ScriptedServer(scenario.answers)
        try:
            client = OpenAICompatibleClient(
                server.url,
                scenario.model,
                temperature=scenario.temperature,
                timeout=30,
                api_key=scenario.api_key,
                reasoning_effort=scenario.reasoning_effort,
                seed=scenario.seed,
            )
            values: list[Any] = []
            errors: list[str] = []
            for call in scenario.calls:
                client.last_error = ""
                values.append(
                    client.chat_json(
                        call.system, call.user, call.schema, max_tokens=call.max_tokens
                    )
                )
                errors.append(client.last_error)
        finally:
            server.close()
        results[scenario.name] = {
            "bodies": [body.decode("ascii") for body in server.bodies],
            "values": values,
            "errors": errors,
        }
    return {"source_commit": SOURCE_COMMIT, "scenarios": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", type=Path)
    group.add_argument("--check", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(run(args.source), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.write is not None:
        args.write.write_text(rendered, encoding="utf-8")
        print(f"snapshot written: {len(SCENARIOS)} scenarios")
        return 0
    if args.check.read_text(encoding="utf-8") != rendered:
        print("the source run differs from the snapshot", file=sys.stderr)
        return 1
    print(f"the source run equals the snapshot byte for byte: {len(SCENARIOS)} scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
