"""CLI: an index that does not fit the dictionary is noticed (``vsa serve`` builds it first)."""

from __future__ import annotations

import json
from pathlib import Path

from vsa.cli import _index_problem
from vsa.config import Settings
from vsa.pipeline import Engine


def test_index_problem(sample_store_path: Path, tmp_path: Path) -> None:
    s = Settings()
    s.dictionary.store = str(sample_store_path)
    s.index.dir = str(tmp_path / "index")
    assert _index_problem(s) == "indeks yok"

    Engine.from_dictionary_file(s).save()
    assert _index_problem(s) == ""

    text = sample_store_path.read_text(encoding="utf-8")
    sample_store_path.write_text(text.replace("Tekrar.", "Değişti."), encoding="utf-8")
    assert "değişmiş" in _index_problem(s)  # a hand edit gives the store a new version

    meta = tmp_path / "index" / "meta.json"
    meta.write_text(json.dumps({"format": 0}), encoding="utf-8")
    assert _index_problem(s) == "indeks formatı eski"
    meta.write_text("{bozuk", encoding="utf-8")
    assert _index_problem(s) == "indeks okunamadı"


def test_no_dictionary_yet(tmp_path: Path) -> None:
    """ADR-050: before the first import the app starts, empty, and says what to do."""
    s = Settings()
    s.dictionary.store = str(tmp_path / "yok.jsonl")
    s.index.dir = str(tmp_path / "index")
    engine = Engine.from_dictionary_file(s)
    meta = engine.save()
    assert meta["columns"] == 0 and _index_problem(s) == ""
    engine = Engine.from_index(s)
    assert engine.rank_objects("kredi kartı limit")[0] == []
    r = engine.analyze("kredi kartı limit")
    assert r.objects == [] and "içe aktarılmadı" in r.summary
