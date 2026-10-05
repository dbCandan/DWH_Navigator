"""Vector index rebuild from the admin screen: the same build as ``vsa index --dense``,
run as a background job with progress and a stop button. One build at a time; the
engine keeps answering with the old vectors until the build is done, then reloads.

Stopping or a failure loses nothing: the embedding cache keeps every finished batch and
the next start continues from there (as long as the embedding model is the same).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Protocol

from vsa import cancel
from vsa.config import load_settings
from vsa.index.dense import META_FILE, build_all, column_staleness
from vsa.llm.client import LLMError, embedding_client
from vsa.pipeline import Engine

log = logging.getLogger(__name__)

PHASES = ("columns", "objects")


class Host(Protocol):
    engine: Engine
    settings_path: Path

    def reload(self) -> None: ...


class DenseBuilder:
    def __init__(self, host: Host) -> None:
        self.host = host
        self._lock = threading.Lock()
        self._token: cancel.Token | None = None
        self.job: dict[str, Any] | None = None

    @property
    def running(self) -> bool:
        return self.job is not None and self.job["status"] == "running"

    def _meta(self) -> dict[str, Any]:
        path = Path(self.host.engine.settings.index.dir) / META_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _need(self, model: str, meta: dict[str, Any]) -> str:
        """Why the vector index should be (re)built; "" when it matches."""
        if not model:
            return ""
        if not meta:
            return "Vektör indeksi hiç kurulmadı"
        if meta.get("model") != model:
            return f"İndeks “{meta.get('model')}” ile kuruldu; bağlı embedding modeli “{model}”"
        stale = column_staleness(meta, self.host.engine.dictionary.columns)
        if stale:
            return f"Sözlük değişti; {stale} kolonun vektörü yok ya da eski"
        return ""

    def state(self) -> dict[str, Any]:
        engine = self.host.engine
        model = engine.settings.llm.embedding_model
        meta = self._meta()
        job = dict(self.job) if self.job else None
        if job and job["status"] == "running":
            job["elapsed_ms"] = round((time.time() - job["started"]) * 1000)
            first = job["first_done"]  # None until the first progress report
            fresh = job["done"] - first if first is not None else 0
            if fresh > 0:
                left = job["total"] - job["done"]
                job["eta_ms"] = round((time.time() - job["started"]) / fresh * left * 1000)
        return {
            "model": model,
            "index_model": meta.get("model", ""),
            "index_columns": meta.get("columns"),
            "built": bool(meta),
            "need": self._need(model, meta),
            "hybrid": engine.hybrid,
            "dense_enabled": engine.settings.dense.enabled,
            "job": job,
        }

    # ------------------------------------------------------------------ actions

    def start(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            if self.running:
                raise ValueError("Vektör indeksi zaten kuruluyor")
            settings = load_settings(self.host.settings_path)
            try:
                client = embedding_client(settings.llm)
                client.ping()
            except LLMError as exc:
                raise ValueError(f"Embedding sunucusuna ulaşılamadı: {exc}") from exc
            engine = self.host.engine
            columns = list(engine.dictionary.columns)
            objects = {k: [f.col for f in o.features] for k, o in engine.objects.items()}
            model = settings.llm.embedding_model
            self._token = token = cancel.Token()
            self.job = {
                "status": "running",
                "model": model,
                "phase": "columns",
                "done": 0,
                "first_done": None,
                "total": len(columns) + len(objects),
                "columns": len(columns),
                "objects": len(objects),
                "started": time.time(),
                "finished": None,
                "error": "",
            }
            job = self.job

            def progress(phase: str, done: int, total: int) -> None:
                overall = done + (len(columns) if phase == "objects" else 0)
                if job["first_done"] is None:
                    job["first_done"] = overall  # vectors already in the cache
                job["phase"], job["done"] = phase, overall

            def run() -> None:
                try:
                    with cancel.using(token):
                        build_all(columns, objects, client, model, Path(settings.index.dir),
                                  progress=progress)  # fmt: skip
                    self.host.reload()
                    job["status"] = "done"
                except cancel.Cancelled:
                    job["status"] = "cancelled"
                except LLMError as exc:
                    job["status"], job["error"] = ("cancelled", "") if token.cancelled else (
                        "error", str(exc))  # fmt: skip
                except Exception as exc:  # the job must always end in a final state
                    log.exception("Vektör indeksi kurulamadı")
                    job["status"], job["error"] = "error", str(exc)
                finally:
                    job["finished"] = time.time()
                    if job["first_done"] is None:
                        job["first_done"] = 0

            threading.Thread(target=run, name="dense-build", daemon=True).start()
        return self.state()

    def cancel(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.running and self._token is not None:
            self._token.cancel()
        return self.state()
