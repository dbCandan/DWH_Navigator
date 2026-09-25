"""Dense vector index over dictionary columns (HANDOVER §5, M3). Does file I/O.

Vectors come from a local embedding model (BGE-M3 via an OpenAI-compatible server).
The build is resumable: each column's vector is cached under a hash of its text and the
model name, so an interrupted build continues where it stopped and a dictionary update
only re-embeds changed columns.

Per ADR-004 the dense arm is queried with the user's ORIGINAL wording, not the
synonym-expanded one.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vsa.llm.client import LLMClient
from vsa.models import DictColumn
from vsa.text.normalize import split_camel

log = logging.getLogger(__name__)

VECTORS_FILE = "dense_vectors.npy"
META_FILE = "dense_meta.json"


def column_text(col: DictColumn) -> str:
    """What the embedding model sees for one column."""
    name = " ".join(split_camel(col.column))
    parts = [f"{col.column} ({name})", col.description]
    if col.synonyms:
        parts.append("Eş anlamlılar: " + ", ".join(col.synonyms))
    parts.append(f"Tablo: {col.object_name}")
    return " | ".join(p for p in parts if p)


def text_key(model: str, text: str) -> str:
    return hashlib.sha1(f"{model}\n{text}".encode()).hexdigest()


@dataclass(slots=True)
class DenseIndex:
    vectors: np.ndarray  # (n_columns, dim), L2-normalized float32; row i == column id i
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
    for start in range(0, len(missing), batch_size):
        chunk = missing[start : start + batch_size]
        vectors = client.embed([texts[i] for i in chunk])
        for i, vec in zip(chunk, vectors, strict=True):
            cache[keys[i]] = np.asarray(vec, dtype=np.float32)
        done += len(chunk)
        if progress:
            progress(done, len(keys))
        if (start // batch_size) % 10 == 9:
            _save_cache(directory, model, cache)  # checkpoint every ~10 batches
    _save_cache(directory, model, cache)

    matrix = normalize(np.stack([cache[k] for k in keys]))
    np.save(directory / VECTORS_FILE, matrix)
    (directory / META_FILE).write_text(
        json.dumps({"model": model, "columns": len(keys), "dim": int(matrix.shape[1])}),
        encoding="utf-8",
    )
    return DenseIndex(matrix, model)


def load_dense_index(directory: Path, n_columns: int) -> DenseIndex | None:
    meta_path = directory / META_FILE
    if not meta_path.exists() or not (directory / VECTORS_FILE).exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    vectors = np.load(directory / VECTORS_FILE)
    if vectors.shape[0] != n_columns:
        log.warning("Vektör indeksi sözlükle uyumsuz (%d ≠ %d); `vsa index --dense` çalıştırın",
                    vectors.shape[0], n_columns)  # fmt: skip
        return None
    return DenseIndex(vectors.astype(np.float32), str(meta["model"]))


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
