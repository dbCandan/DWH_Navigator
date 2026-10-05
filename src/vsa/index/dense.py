"""Dense vector index over dictionary columns (HANDOVER §5, M3). Does file I/O.

Vectors come from a local embedding model (BGE-M3 via an OpenAI-compatible server).
The build is resumable: each column's vector is cached under a hash of its text and the
model name, so an interrupted build continues where it stopped and a dictionary update
only re-embeds changed columns. A build started from the admin screen runs under a
``cancel.Token``: "Durdur" stops it between batches and the cache keeps what was done.

Per ADR-004 the dense arm is queried with the user's ORIGINAL wording, not the
synonym-expanded one.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vsa import cancel
from vsa.llm.client import LLMClient
from vsa.models import DictColumn
from vsa.text.normalize import split_camel

log = logging.getLogger(__name__)

VECTORS_FILE = "dense_vectors.npy"
META_FILE = "dense_meta.json"
OBJECT_VECTORS_FILE = "object_vectors.npy"
OBJECT_META_FILE = "object_meta.json"
OBJECT_TEXT_COLUMNS = 60
OBJECT_TEXT_SYNONYMS = 40


def column_text(col: DictColumn) -> str:
    """What the embedding model sees for one column."""
    name = " ".join(split_camel(col.column))
    parts = [f"{col.column} ({name})", col.description]
    if col.synonyms:
        parts.append("Eş anlamlılar: " + ", ".join(col.synonyms))
    parts.append(f"Tablo: {col.object_name}")
    return " | ".join(p for p in parts if p)


def object_text(columns: Sequence[DictColumn]) -> str:
    """What the embedding model sees for one table (ADR-028): its name spelled out,
    its column names and the Turkish synonyms the dictionary gives them. The model is
    multilingual, so a Turkish request meets English table and column names here."""
    first = columns[0]
    parts = [f"Tablo: {first.object_name} ({' '.join(split_camel(first.object_name))})"]
    names = [" ".join(split_camel(c.column)) for c in columns[:OBJECT_TEXT_COLUMNS]]
    parts.append("Kolonlar: " + ", ".join(names))
    synonyms: list[str] = []
    for c in columns:
        for s in c.synonyms:
            if s not in synonyms:
                synonyms.append(s)
    if synonyms:
        parts.append("Eş anlamlılar: " + ", ".join(synonyms[:OBJECT_TEXT_SYNONYMS]))
    return " | ".join(parts)


def text_key(model: str, text: str) -> str:
    return hashlib.sha1(f"{model}\n{text}".encode()).hexdigest()


@dataclass(slots=True)
class DenseIndex:
    vectors: np.ndarray  # (n_columns, dim), L2-normalized float32; row i == column id i
    # (rows are matched to columns by text hash at load, never by file position)
    model: str

    @property
    def dim(self) -> int:
        return int(self.vectors.shape[1])

    def search(self, query: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        sims = self.vectors @ query
        k = min(top_k, len(sims))
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [(int(i), float(sims[i])) for i in idx]

    def similarity(self, query: np.ndarray, ids: Sequence[int]) -> dict[int, float]:
        sims = self.vectors[list(ids)] @ query
        return {int(i): float(s) for i, s in zip(ids, sims, strict=True)}


def normalize(v: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(v, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    out: np.ndarray = (v / norms).astype(np.float32)
    return out


def build_dense_index(
    columns: Sequence[DictColumn],
    client: LLMClient,
    model: str,
    directory: Path,
    batch_size: int = 64,
    progress: Callable[[int, int], None] | None = None,
) -> DenseIndex:
    """Embed every column (reusing cached vectors) and save; resumable."""
    directory.mkdir(parents=True, exist_ok=True)
    cache = _load_cache(directory, model)
    texts = [column_text(c) for c in columns]
    keys = [text_key(model, t) for t in texts]
    missing = [i for i, k in enumerate(keys) if k not in cache]
    log.info(
        "Vektör: %d kolon, %d önbellekte, %d hesaplanacak",
        len(keys),
        len(keys) - len(missing),
        len(missing),
    )

    done = len(keys) - len(missing)
    if progress:
        progress(done, len(keys))
    try:
        for start in range(0, len(missing), batch_size):
            cancel.check()
            chunk = missing[start : start + batch_size]
            vectors = client.embed([texts[i] for i in chunk])
            for i, vec in zip(chunk, vectors, strict=True):
                cache[keys[i]] = np.asarray(vec, dtype=np.float32)
            done += len(chunk)
            if progress:
                progress(done, len(keys))
            if (start // batch_size) % 10 == 9:
                _save_cache(directory, model, cache)  # checkpoint every ~10 batches
    finally:
        _save_cache(directory, model, cache)  # a stopped or failed build resumes from here

    matrix = normalize(np.stack([cache[k] for k in keys]))
    np.save(directory / VECTORS_FILE, matrix)
    meta = {"model": model, "columns": len(keys), "dim": int(matrix.shape[1]), "keys": keys}
    (directory / META_FILE).write_text(json.dumps(meta), encoding="utf-8")
    return DenseIndex(matrix, model)


@dataclass(slots=True)
class ObjectDenseIndex:
    """One vector per table (ADR-028); row i belongs to ``keys[i]``."""

    keys: list[str]
    vectors: np.ndarray
    model: str

    def similarity(self, query: np.ndarray) -> dict[str, float]:
        sims = self.vectors @ query
        return {k: float(s) for k, s in zip(self.keys, sims, strict=True)}


def build_object_index(
    objects: Mapping[str, Sequence[DictColumn]],
    client: LLMClient,
    model: str,
    directory: Path,
    batch_size: int = 16,
    progress: Callable[[int, int], None] | None = None,
) -> ObjectDenseIndex:
    """Embed every table profile (sharing the column vector cache) and save."""
    directory.mkdir(parents=True, exist_ok=True)
    cache = _load_cache(directory, model)
    keys = sorted(objects)
    texts = [object_text(objects[k]) for k in keys]
    hashes = [text_key(model, t) for t in texts]
    missing = [i for i, h in enumerate(hashes) if h not in cache]
    done = len(keys) - len(missing)
    if progress:
        progress(done, len(keys))
    try:
        for start in range(0, len(missing), batch_size):
            cancel.check()
            chunk = missing[start : start + batch_size]
            for i, vec in zip(chunk, client.embed([texts[i] for i in chunk]), strict=True):
                cache[hashes[i]] = np.asarray(vec, dtype=np.float32)
            done += len(chunk)
            if progress:
                progress(done, len(keys))
    finally:
        _save_cache(directory, model, cache)
    matrix = normalize(np.stack([cache[h] for h in hashes]))
    np.save(directory / OBJECT_VECTORS_FILE, matrix)
    (directory / OBJECT_META_FILE).write_text(
        json.dumps({"model": model, "keys": keys, "hashes": hashes}), encoding="utf-8"
    )
    return ObjectDenseIndex(keys, matrix, model)


def build_all(
    columns: Sequence[DictColumn],
    objects: Mapping[str, Sequence[DictColumn]],
    client: LLMClient,
    model: str,
    directory: Path,
    progress: Callable[[str, int, int], None] | None = None,
) -> None:
    """Column vectors, then table profile vectors (ADR-028) — what ``vsa index --dense``
    and the admin screen's button build. ``progress(phase, done, total)``, phase is
    ``"columns"`` or ``"objects"``."""

    def step(phase: str) -> Callable[[int, int], None] | None:
        return None if progress is None else lambda done, total: progress(phase, done, total)

    build_dense_index(columns, client, model, directory, progress=step("columns"))
    build_object_index(objects, client, model, directory, progress=step("objects"))


def _rows_by_hash(stored: Sequence[str], wanted: Sequence[str]) -> list[int] | None:
    """Row of each wanted text hash in the stored index, or None if any is missing."""
    pos = {h: i for i, h in enumerate(stored)}
    rows = [pos.get(h) for h in wanted]
    return None if any(r is None for r in rows) else [r for r in rows if r is not None]


def column_staleness(meta: Mapping[str, object], columns: Sequence[DictColumn]) -> int:
    """How many columns have no vector for their current text: a new column, a changed
    description or synonym, or an index saved before hashes were kept (all count). 0 = fresh."""
    stored = meta.get("keys")
    if not isinstance(stored, list):
        return len(columns)
    model = str(meta.get("model", ""))
    have = set(stored)
    return sum(text_key(model, column_text(c)) not in have for c in columns)


def load_object_index(
    directory: Path, objects: Mapping[str, Sequence[DictColumn]]
) -> ObjectDenseIndex | None:
    meta_path = directory / OBJECT_META_FILE
    if not meta_path.exists() or not (directory / OBJECT_VECTORS_FILE).exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    model = str(meta["model"])
    keys = sorted(objects)
    stored = meta.get("hashes")
    rows = (
        _rows_by_hash(stored, [text_key(model, object_text(objects[k])) for k in keys])
        if isinstance(stored, list) and len(stored) == len(meta["keys"])
        else None
    )
    if rows is None:
        log.warning("Tablo vektörleri sözlükle uyumsuz; `vsa index --dense` çalıştırın")
        return None
    vectors = np.load(directory / OBJECT_VECTORS_FILE).astype(np.float32)
    return ObjectDenseIndex(keys, vectors[rows], model)


def load_dense_index(directory: Path, columns: Sequence[DictColumn]) -> DenseIndex | None:
    """Column vectors in dictionary order, matched by text hash: reordering the dictionary
    is harmless, and a changed or new column makes the index stale (None) instead of
    silently pairing a column with another column's vector."""
    meta_path = directory / META_FILE
    if not meta_path.exists() or not (directory / VECTORS_FILE).exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    model = str(meta["model"])
    stored = meta.get("keys")
    vectors = np.load(directory / VECTORS_FILE)
    rows = (
        _rows_by_hash(stored, [text_key(model, column_text(c)) for c in columns])
        if isinstance(stored, list) and len(stored) == vectors.shape[0]
        else None
    )
    if rows is None:
        log.warning("Vektör indeksi sözlükle uyumsuz (%d kolonun vektörü yok ya da eski); "
                    "`vsa index --dense` çalıştırın", column_staleness(meta, columns))  # fmt: skip
        return None
    return DenseIndex(vectors[rows].astype(np.float32), model)


# --------------------------------------------------------------------------- cache


def _cache_paths(directory: Path) -> tuple[Path, Path]:
    return directory / "dense_cache.npy", directory / "dense_cache_keys.json"


def _load_cache(directory: Path, model: str) -> dict[str, np.ndarray]:
    vec_path, key_path = _cache_paths(directory)
    if not vec_path.exists() or not key_path.exists():
        return {}
    meta = json.loads(key_path.read_text(encoding="utf-8"))
    if meta.get("model") != model:
        return {}
    matrix = np.load(vec_path)
    return {k: matrix[i] for i, k in enumerate(meta["keys"])}


def _save_cache(directory: Path, model: str, cache: dict[str, np.ndarray]) -> None:
    if not cache:
        return
    vec_path, key_path = _cache_paths(directory)
    keys = list(cache)
    np.save(vec_path, np.stack([cache[k] for k in keys]))
    key_path.write_text(json.dumps({"model": model, "keys": keys}), encoding="utf-8")
