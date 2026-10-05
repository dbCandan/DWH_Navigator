"""Index persistence under ``data/index/`` (HANDOVER §18.2). Does file I/O.

columns.json         normalized column records
bm25.json            BM25 postings and document lengths
objects.json         object profiles (the object sheet: description, grain, keys…)
synonym_index.json   synonym phrase -> column ids (for inspection/debug)
meta.json            dictionary sha/version, row count, build time, settings digest
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from vsa.index.bm25 import BM25Index
from vsa.models import DictColumn, Dictionary, Flag, FlagKind, ObjectProfile

INDEX_FORMAT = 1


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
        raw_description=d["raw_description"],
        synonyms=tuple(d["synonyms"]),
        flags=tuple(Flag(FlagKind(f["kind"]), f["text"]) for f in d["flags"]),
        dataset_group=d["dataset_group"],
        has_pii=bool(d["has_pii"]),
        role=d.get("role", ""),
        summary=d.get("summary", ""),
    )


def _profile_from_dict(d: dict[str, Any]) -> ObjectProfile:
    return ObjectProfile(
        key=d["key"],
        description=d.get("description", ""),
        grain=d.get("grain", ""),
        key_columns=tuple(d.get("key_columns", ())),
        time_columns=tuple(d.get("time_columns", ())),
        domain=d.get("domain", ""),
        group=d.get("group", ""),
    )


def settings_digest(parts: dict[str, Any]) -> str:
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def save_index(
    directory: Path,
    dictionary: Dictionary,
    bm25: BM25Index,
    synonym_index: dict[tuple[str, ...], list[int]],
    index_settings: dict[str, Any],
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)

    def dump(name: str, obj: Any) -> None:
        (directory / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    dump("columns.json", [asdict(c) for c in dictionary.columns])
    dump("objects.json", [asdict(p) for p in dictionary.objects.values()])
    dump("bm25.json", bm25.to_dict())
    dump("synonym_index.json", {" ".join(k): v for k, v in synonym_index.items()})
    meta = {
        "format": INDEX_FORMAT,
        "dictionary_source": dictionary.source_path,
        "dictionary_version": dictionary.version,
        "columns": len(dictionary.columns),
        "objects": len(dictionary.object_keys),
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "settings_digest": settings_digest(index_settings),
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
    objects_path = directory / "objects.json"
    profiles = (
        [_profile_from_dict(p) for p in json.loads(objects_path.read_text(encoding="utf-8"))]
        if objects_path.exists()
        else []
    )
    bm25 = BM25Index.from_dict(json.loads((directory / "bm25.json").read_text(encoding="utf-8")))
    dictionary = Dictionary(
        columns=[_column_from_dict(c) for c in cols],
        source_path=meta["dictionary_source"],
        version=meta["dictionary_version"],
        warnings=list(meta.get("warnings", [])),
        objects={p.key: p for p in profiles},
    )
    return dictionary, bm25, meta
