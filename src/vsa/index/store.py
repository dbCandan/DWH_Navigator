"""Index persistence under ``data/index/``. Does file I/O.

columns.json         normalized column records
bm25.json            BM25 postings and document lengths
objects.json         object profiles (the object sheet: description, grain, time columns…)
meta.json            dictionary version, row count, build time

An index of another format is rebuilt (``vsa serve`` does it on start).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from vsa.index.bm25 import BM25Index
from vsa.models import DictColumn, Dictionary, ObjectProfile

INDEX_FORMAT = 2


class IndexMissingError(FileNotFoundError):
    pass


def _column_from_dict(d: dict[str, Any]) -> DictColumn:
    return DictColumn(
        id=int(d["id"]),
        database=d["database"],
        schema=d["schema"],
        object_name=d["object_name"],
        column=d["column"],
        description=d["description"],
        synonyms=tuple(d["synonyms"]),
        dataset_group=d["dataset_group"],
        has_pii=bool(d["has_pii"]),
        role=d["role"],
        summary=d["summary"],
    )


def _profile_from_dict(d: dict[str, Any]) -> ObjectProfile:
    return ObjectProfile(
        key=d["key"],
        description=d["description"],
        grain=d["grain"],
        time_columns=tuple(d["time_columns"]),
        domain=d["domain"],
        group=d["group"],
    )


def save_index(directory: Path, dictionary: Dictionary, bm25: BM25Index) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)

    def dump(name: str, obj: Any) -> None:
        (directory / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    dump("columns.json", [asdict(c) for c in dictionary.columns])
    dump("objects.json", [asdict(p) for p in dictionary.objects.values()])
    dump("bm25.json", bm25.to_dict())
    meta = {
        "format": INDEX_FORMAT,
        "dictionary_source": dictionary.source_path,
        "dictionary_version": dictionary.version,
        "columns": len(dictionary.columns),
        "objects": len(dictionary.object_keys),
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "warnings": dictionary.warnings,
    }
    dump("meta.json", meta)
    return meta


def load_index(directory: Path) -> tuple[Dictionary, BM25Index, dict[str, Any]]:
    meta_path = directory / "meta.json"
    if not meta_path.exists():
        raise IndexMissingError(
            f"İndeks bulunamadı: {directory}. Önce `vsa index` komutunu çalıştırın."
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("format") != INDEX_FORMAT:
        raise IndexMissingError("İndeks formatı eski; `vsa index` ile yeniden kurun.")
    cols = json.loads((directory / "columns.json").read_text(encoding="utf-8"))
    profiles = [
        _profile_from_dict(p)
        for p in json.loads((directory / "objects.json").read_text(encoding="utf-8"))
    ]
    bm25 = BM25Index.from_dict(json.loads((directory / "bm25.json").read_text(encoding="utf-8")))
    dictionary = Dictionary(
        columns=[_column_from_dict(c) for c in cols],
        source_path=meta["dictionary_source"],
        version=meta["dictionary_version"],
        warnings=list(meta["warnings"]),
        objects={p.key: p for p in profiles},
    )
    return dictionary, bm25, meta
