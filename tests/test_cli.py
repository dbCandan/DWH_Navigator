"""CLI: an index that does not fit the dictionary file is noticed (``serve --auto-index``)."""

from __future__ import annotations

import json
from pathlib import Path

from vsa.cli import _index_problem
from vsa.config import Settings
from vsa.pipeline import Engine


def test_index_problem(sample_dictionary_path: Path, tmp_path: Path) -> None:
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    s.index.dir = str(tmp_path / "index")
    assert _index_problem(s) == "indeks yok"

    Engine.from_dictionary_file(s).save()
    assert _index_problem(s) == ""

    sample_dictionary_path.write_bytes(sample_dictionary_path.read_bytes() + b"\0")
    assert "değişmiş" in _index_problem(s)

    meta = tmp_path / "index" / "meta.json"
    meta.write_text(json.dumps({"format": 0}), encoding="utf-8")
    assert _index_problem(s) == "indeks formatı eski"
    meta.write_text("{bozuk", encoding="utf-8")
    assert _index_problem(s) == "indeks okunamadı"
