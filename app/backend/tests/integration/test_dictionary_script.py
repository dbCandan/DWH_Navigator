"""The backend's dictionary script (dictionary-management Requirement 16).

``python -m app.scripts.dictionary export`` writes the active version; refusals go to standard
error with exit code 2. ``import`` and ``template`` are gone (dictionary-sync Requirement 13).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.analysis.dictionary_workbook import from_workbook
from tests.integration.data_dictionary import SYNTHETIC_WORKBOOK, DataDictionary

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]


def run(module: str, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=BACKEND,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        timeout=120,
        check=False,
    )


def script(*args: str) -> subprocess.CompletedProcess[bytes]:
    return run("app.scripts.dictionary", *args)


async def test_export_from_the_command_line(dd: DataDictionary, tmp_path: Path) -> None:
    imported = from_workbook(SYNTHETIC_WORKBOOK.read_bytes())
    seeded = run("tests.dictionary_seed", str(SYNTHETIC_WORKBOOK))  # the e2e scenarios' seeder
    assert seeded.returncode == 0, seeded.stderr
    state = (await dd.get("/dictionary")).json()
    assert state["active"]["channel"] == "betik" and state["active"]["imported_by"] is None
    assert state["active"]["source_name"] == "sozluk_sentetik.xlsx"
    assert state["index_dictionary_version"] == ""  # the running index was not rebuilt
    index = (await dd.get("/search-index")).json()
    assert index["state"] == "stale" and index["stale_inputs"] == ["dictionary"]

    again = run("tests.dictionary_seed", str(SYNTHETIC_WORKBOOK))
    assert again.returncode == 0
    assert again.stdout.decode("utf-8").strip() == f"Değişmedi: {imported.version}"

    out = tmp_path / "disari.xlsx"
    exported = script("export", str(out))
    assert exported.returncode == 0 and exported.stdout.decode("utf-8").strip() == f"Yazıldı: {out}"
    assert from_workbook(out.read_bytes()).digest == imported.digest
    to_stdout = script("export", "-")
    assert from_workbook(to_stdout.stdout).digest == imported.digest


async def test_refusals_go_to_standard_error_with_exit_code_2(
    dd: DataDictionary, tmp_path: Path
) -> None:
    missing = script("export", str(tmp_path / "x.xlsx"))
    assert missing.returncode == 2
    assert missing.stderr.decode("utf-8").strip().endswith("Sözlük henüz içe aktarılmadı.")
    assert (await dd.get("/dictionary")).json()["active"] is None


def test_import_and_template_are_no_longer_commands() -> None:
    for command in ("import", "template"):
        refused = script(command, str(SYNTHETIC_WORKBOOK))
        assert refused.returncode == 2 and b"invalid choice" in refused.stderr
