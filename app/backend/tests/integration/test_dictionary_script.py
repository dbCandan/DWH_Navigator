"""The backend's dictionary script (dictionary-management Requirement 16).

``python -m app.scripts.dictionary import|export|template`` with the screen's rules and lock: no
importing user, channel ``betik``, the running index left stale, refusals on standard error with
exit code 2.
"""

import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.db.session import engine
from app.infrastructure.repositories.dictionary_repository import IMPORT_LOCK_KEY
from app.services.analysis.dictionary_workbook import from_workbook
from tests.integration.data_dictionary import SYNTHETIC_WORKBOOK, DataDictionary

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]


def script(*args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "app.scripts.dictionary", *args],
        cwd=BACKEND,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        input=stdin,
        capture_output=True,
        timeout=120,
        check=False,
    )


async def test_import_export_and_template_from_the_command_line(
    dd: DataDictionary, tmp_path: Path
) -> None:
    imported = from_workbook(SYNTHETIC_WORKBOOK.read_bytes())
    first = script("import", str(SYNTHETIC_WORKBOOK))
    assert first.returncode == 0, first.stderr
    lines = first.stdout.decode("utf-8").splitlines()
    assert lines[0] == f"Aktarıldı: 1.557 kolon · 87 tablo (sürüm {imported.version})"
    assert lines[1:4] == [f"• {w}" for w in imported.warnings[:3]]
    assert lines[-1] == (
        "Çalışan uygulama yeni sözlüğü indeks yeniden kurulunca kullanır "
        "(Yönetim → Bakım → İndeksi yeniden kur)."
    )
    state = (await dd.get("/dictionary")).json()
    assert state["active"]["channel"] == "betik" and state["active"]["imported_by"] is None
    assert state["active"]["source_name"] == "sozluk_sentetik.xlsx"
    assert state["index_dictionary_version"] == ""  # the running index was not rebuilt
    index = (await dd.get("/search-index")).json()
    assert index["state"] == "stale" and index["stale_inputs"] == ["dictionary"]

    again = script("import", "-", stdin=SYNTHETIC_WORKBOOK.read_bytes())
    assert again.returncode == 0
    assert again.stdout.decode("utf-8").strip() == (
        f"Değişmedi: içerik etkin sürümle aynı (sürüm {imported.version})"
    )

    out = tmp_path / "disari.xlsx"
    exported = script("export", str(out))
    assert exported.returncode == 0 and exported.stdout.decode("utf-8").strip() == f"Yazıldı: {out}"
    assert from_workbook(out.read_bytes()).digest == imported.digest
    to_stdout = script("export", "-")
    assert from_workbook(to_stdout.stdout).digest == imported.digest
    template = script("template", "-")
    assert load_workbook(BytesIO(template.stdout)).sheetnames == ["Objeler", "Kolonlar"]


async def test_refusals_go_to_standard_error_with_exit_code_2(
    dd: DataDictionary, tmp_path: Path
) -> None:
    missing = script("export", str(tmp_path / "x.xlsx"))
    assert missing.returncode == 2
    assert missing.stderr.decode("utf-8").strip().endswith("Sözlük henüz içe aktarılmadı.")
    bad = tmp_path / "bozuk.xlsx"
    bad.write_bytes(b"not a workbook")
    refused = script("import", str(bad))
    assert refused.returncode == 2
    assert "Dosya Excel (.xlsx) olarak okunamadı." in refused.stderr.decode("utf-8")
    empty = script("import", "-", stdin=b"")
    assert empty.returncode == 2 and "Dosya boş" in empty.stderr.decode("utf-8")

    async with engine.connect() as holder:
        await holder.execute(text("BEGIN"))
        await holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": IMPORT_LOCK_KEY})
        locked = script("import", str(SYNTHETIC_WORKBOOK))
        await holder.execute(text("ROLLBACK"))
    assert locked.returncode == 2
    assert "Başka bir sözlük içe aktarması sürüyor; bitince yeniden deneyin." in (
        locked.stderr.decode("utf-8")
    )
    assert (await dd.get("/dictionary")).json()["active"] is None
