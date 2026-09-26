"""Local web server (M6). Standard library only — nothing extra to ship into a closed
network. One engine, one lock: the tool serves a team, not the internet.

    GET  /                      single-page UI (static/index.html, no external assets)
    GET  /api/status            dictionary / search / LLM status
    POST /api/ask               {"query": "...", "top": 5}
    POST /api/batch             raw .xlsx body (X-Filename header) or {"fields": [...]}
    GET  /api/report/<id>       Excel report of an earlier ask/batch result
    GET  /api/objects?q=...     dictionary explorer: objects matching a name
    GET  /api/object/<key>      all columns of one object
    GET  /api/galaxy            all objects with their dataset group (star map)
    POST /api/feedback          {"query", "object", "vote": "up"|"down", "note"} (M7)
    GET  /ayarlar               settings screen (static/settings.html)
    GET  /api/settings          schema + current values + models offered by LM Studio
    POST /api/settings          {"values": {...}} validate, write config/settings.yaml, reload
    POST /api/settings/test     try endpoint / chat model / embedding model from the form
    POST /api/reindex           rebuild the BM25 index with the saved settings
    GET  /api/cloud-models      chat models of the hosted catalog (lab only, ADR-026)
    GET  /api/lab               model lab: ranked results + live progress (ADR-025)
    POST /api/lab/start         {"models": [...], "temps": "0,0.1", "runs": 2} → `vsa lab`
    POST /api/lab/stop          stop the running lab after its current call
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from vsa import lab
from vsa.batch import BatchAnalyzer
from vsa.config import CLOUD_PREFIX, DEFAULT_SETTINGS_PATH, cloud_api_key, load_settings
from vsa.llm.client import LLMError, OpenAICompatibleClient
from vsa.loader import load_request_file
from vsa.models import AnalysisResult, BatchResult, RequestField
from vsa.pipeline import Engine
from vsa.report.excel import report_path, write_ask_report, write_batch_report
from vsa.text.normalize import fold
from vsa.web import serialize
from vsa.web.settings_schema import (
    DENSE,
    FIELDS,
    REINDEX,
    SECRET_KEYS,
    SECTIONS,
    coerce,
    defaults,
    get_path,
    is_chat_model,
    to_yaml_tree,
    values_of,
)

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 20 * 1024 * 1024
MAX_REPORTS = 50
EXPLORER_LIMIT = 60
EXPLORER_CONTENT_LIMIT = 25  # objects from the content (search pipeline) layer
MIN_CONTENT_QUERY = 3  # shorter input: name matching only
LAB_STALE_SEC = 1800  # no progress for this long: the lab process is gone
LAB_LOG = Path("data/logs/lab.log")


class App:
    def __init__(
        self,
        engine: Engine,
        out_dir: Path,
        feedback_path: Path,
        settings_path: Path | None = None,
    ) -> None:
        self.engine = engine
        self.out_dir = out_dir
        self.feedback_path = feedback_path
        self.settings_path = settings_path or DEFAULT_SETTINGS_PATH
        self.reindex_pending: list[str] = []
        self._lab_proc: subprocess.Popen[bytes] | None = None
        self._cloud_cache: tuple[float, str, dict[str, Any]] | None = None
        self.lab_results, self.lab_progress = lab.RESULTS_PATH, lab.PROGRESS_PATH
        self.lab_stop_flag = lab.STOP_PATH
        self.lock = threading.Lock()
        self.results: dict[str, AnalysisResult | BatchResult] = {}
        self.object_index = self._object_index()

    def _object_index(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, obj in self.engine.objects.items():
            first = obj.features[0].col
            groups = sorted({f.col.dataset_group for f in obj.features if f.col.dataset_group})
            rows.append(
                {
                    "key": key,
                    "name": first.object_name,
                    "schema": f"{first.database}.{first.schema}",
                    "columns": len(obj.features),
                    "groups": groups,
                    "_fold": fold(f"{key} {' '.join(groups)}"),
                    "_cols": fold(" ".join(f.col.column for f in obj.features)),
                    "_colnames": [f.col.column for f in obj.features],
                }
            )
        rows.sort(key=lambda r: str(r["name"]))
        return rows

    def _remember(self, result: AnalysisResult | BatchResult) -> str:
        rid = uuid.uuid4().hex[:12]
        self.results[rid] = result
        while len(self.results) > MAX_REPORTS:
            self.results.pop(next(iter(self.results)))
        return rid

    # ------------------------------------------------------------------ endpoints

    def status(self) -> dict[str, Any]:
        e = self.engine
        s = e.settings
        return {
            "dictionary": Path(e.dictionary.source_path).name,
            "version": e.dictionary.version,
            "columns": len(e.dictionary.columns),
            "objects": len(e.objects),
            "hybrid": e.hybrid,
            "embedding_model": e.dense.model if e.dense else "",
            "llm": e.llm.model if e.judge_enabled else "",
            "judge_candidates": s.llm.judge_candidates,
            "examples": [
                "Kredi kartı limit doluluk oranı verisine ihtiyacımız var, nerede?",
                "Müşterilerin risk bilgilerini aylık bazda ve kırılımlı olarak (kredi kartı, "
                "gayrimenkul, ihtiyaç kredisi vb.) gösteren bir tablo mevcut mudur?",
                "Müşteri bazında aylık FAST ve havale transfer adedi ile tutarı",
                "İhtiyaç kredisi kullanan müşterilerin gecikme gün sayısı",
            ],
        }

    def ask(self, body: dict[str, Any]) -> dict[str, Any]:
        query = str(body.get("query", "")).strip()
        if not query:
            raise ValueError("Talep metni boş")
        top = max(1, min(10, int(body.get("top", 5))))
        with self.lock:
            result = self.engine.analyze(query, top_n=top)
        data = serialize.analysis(result)
        data["report_id"] = self._remember(result)
        return data

    def batch(self, fields: list[RequestField], name: str) -> dict[str, Any]:
        if not fields:
            raise ValueError("Talep dosyasında alan bulunamadı (TR başlık / EN başlık / açıklama)")
        with self.lock:
            result = BatchAnalyzer(self.engine).analyze(fields, name)
        data = serialize.batch(result)
        data["report_id"] = self._remember(result)
        return data

    def report(self, rid: str) -> Path:
        result = self.results.get(rid)
        if result is None:
            raise KeyError(rid)
        if isinstance(result, AnalysisResult):
            return write_ask_report(result, report_path(self.out_dir, "ask", result.query))
        return write_batch_report(result, report_path(self.out_dir, "batch", result.name))

    def objects(self, q: str) -> dict[str, Any]:
        """Explorer search: every search layer except the chat model.

        1. name — table / schema / dataset group contains the text (instant, listed first)
        2. content — the full pipeline without the LLM: Turkish normalization, term
           dictionary, dictionary synonyms, BM25, dense (BGE-M3) and object aggregation;
           finds tables by what their columns *mean*, not only by their names
        3. column name — a column name contains the text
        """
        started = time.perf_counter()
        text = q.strip()
        needle = fold(text)
        rows = self.object_index

        def clean(r: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in r.items() if not k.startswith("_")}

        if not needle:
            browse = [{**clean(r), "match": ""} for r in rows[:EXPLORER_LIMIT]]
            return {"query": "", "items": browse, "counts": {}, "concepts": [], "elapsed_ms": 0}

        items: dict[str, dict[str, Any]] = {}
        for r in rows:
            if needle in r["_fold"]:
                items[r["key"]] = {**clean(r), "match": "ad"}

        concepts: list[str] = []
        if len(needle) >= MIN_CONTENT_QUERY:
            # No engine lock: this path only reads (its caches are plain dict get/set,
            # safe under the GIL), so the explorer — and the Evren route's candidate
            # prefetch — stay instant while an LLM-judged question holds the lock.
            ranked, eq = self.engine.rank_objects(text, use_llm=False, limit=EXPLORER_CONTENT_LIMIT)
            concepts = [c.display() for c in eq.concepts]
            by_key = {r["key"]: r for r in rows}
            for m in ranked:
                entry = items.get(m.object_key) or {
                    **clean(by_key[m.object_key]),
                    "match": "içerik",
                }
                entry.update(
                    score=round(m.score, 4),
                    level=m.level.value,
                    matched=[h.col.column for h in m.columns[:5]],
                    covered=m.covered,
                    missing=m.missing,
                    signal=next((s for h in m.columns for s in h.signals), ""),
                )
                items[m.object_key] = entry

        for r in rows:
            if r["key"] in items or needle not in r["_cols"]:
                continue
            cols = [c for c in r["_colnames"] if needle in fold(c)]
            items[r["key"]] = {**clean(r), "match": "kolon adı", "matched": cols[:5]}

        order = {"ad": 0, "içerik": 1, "kolon adı": 2}
        result = sorted(
            items.values(),
            key=lambda i: (order[i["match"]], -float(i.get("score") or 0), str(i["name"])),
        )[:EXPLORER_LIMIT]
        counts: dict[str, int] = {}
        for i in result:
            counts[i["match"]] = counts.get(i["match"], 0) + 1
        return {
            "query": text,
            "items": result,
            "counts": counts,
            "concepts": concepts,
            "hybrid": self.engine.hybrid,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

    # ------------------------------------------------------------------ settings screen

    def _lmstudio_models(self, endpoint: str) -> list[dict[str, Any]]:
        """Models offered by the server; LM Studio's REST API adds type and load state."""
        base = endpoint.rstrip("/").replace("://localhost", "://127.0.0.1")
        root = base[: -len("/v1")] if base.endswith("/v1") else base
        for url, rich in ((f"{root}/api/v0/models", True), (f"{base}/models", False)):
            try:
                with urllib.request.urlopen(url, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8")).get("data", [])
            except (OSError, ValueError):
                continue
            out = []
            for m in data:
                mid = str(m.get("id", ""))
                mtype = (
                    str(m.get("type", "")) if rich else ("embeddings" if "embed" in mid else "llm")
                )
                out.append(
                    {
                        "id": mid,
                        "kind": "embedding" if mtype.startswith("embed") else "chat",
                        "loaded": m.get("state") == "loaded" if rich else None,
                        "arch": m.get("arch", ""),
                        "quant": m.get("quantization", ""),
                        "context": m.get("max_context_length"),
                    }
                )
            return out
        return []

    def cloud_models(self, refresh: bool = False) -> dict[str, Any]:
        """Chat models of the hosted catalog (lab only, ADR-026); cached for 10 minutes."""
        cloud = self.engine.settings.cloud
        key = cloud_api_key(cloud)
        if not cloud.enabled:
            return {"ok": False, "reason": "Bulut ölçümü kapalı (Ayarlar → Bulut modelleri).",
                    "models": []}  # fmt: skip
        if not key:
            return {"ok": False, "reason": "API anahtarı girilmemiş.", "models": []}
        cached = self._cloud_cache
        if cached and not refresh and time.time() - cached[0] < 600 and cached[1] == cloud.endpoint:
            return cached[2]
        req = urllib.request.Request(
            cloud.endpoint.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8")).get("data", [])
        except urllib.error.HTTPError as exc:
            return {"ok": False, "reason": f"Servis HTTP {exc.code} döndürdü (anahtar geçersiz "
                    "olabilir).", "models": []}  # fmt: skip
        except (OSError, ValueError) as exc:
            return {"ok": False, "reason": f"Servise ulaşılamadı: {exc}", "models": []}
        ids = sorted({str(m.get("id", "")).removeprefix("models/") for m in data} - {""})
        models = [
            {"id": CLOUD_PREFIX + mid, "name": mid, "publisher": mid.split("/")[0] if "/" in mid
             else "", "kind": "cloud"}
            for mid in ids if is_chat_model(mid)
        ]  # fmt: skip
        out = {"ok": True, "reason": "", "models": models, "total": len(ids)}
        self._cloud_cache = (time.time(), cloud.endpoint, out)
        return out

    def settings_get(self) -> dict[str, Any]:
        st = self.engine.settings
        raw = asdict(st)
        return {
            "sections": SECTIONS,
            "values": values_of(st),
            "defaults": defaults(),
            "path": str(self.settings_path),
            "has_api_key": bool(st.llm.api_key),
            "has_secret": {k: bool(get_path(raw, k)) for k in SECRET_KEYS},
            "models": self._lmstudio_models(st.llm.endpoint) if st.llm.endpoint else [],
            "status": {
                "hybrid": self.engine.hybrid,
                "judge": self.engine.judge_enabled,
                "llm_model": self.engine.llm.model,
                "dictionary_version": self.engine.dictionary.version,
                "index_built_at": self.engine.index_meta.get("built_at", ""),
            },
            "reindex_pending": self.reindex_pending,
        }

    def settings_save(self, body: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        submitted = body.get("values") or {}
        if not isinstance(submitted, dict):
            raise ValueError("values bekleniyor")
        current = values_of(self.engine.settings)
        new = dict(current)
        errors = []
        for key, value in submitted.items():
            try:
                new[key] = coerce(key, value)
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            raise ValueError("; ".join(errors))
        raw = asdict(self.engine.settings)
        for key in SECRET_KEYS:
            if not new.get(key):
                new[key] = get_path(raw, key)  # blank = keep the saved secret
        changed = [k for k in FIELDS if k not in SECRET_KEYS and new[k] != current[k]]
        changed += [k for k in SECRET_KEYS if submitted.get(k)]

        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# DWH Navigator ayarları — Ayarlar ekranından kaydedildi "
            f"({datetime.now().isoformat(timespec='seconds')}).\n"
            "# Elle de düzenlenebilir; anlamları için: config/settings.example.yaml\n"
        )
        self.settings_path.write_text(
            header + yaml.safe_dump(to_yaml_tree(new), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        settings = load_settings(self.settings_path)
        with self.lock:
            engine = Engine.from_index(settings)
            self.engine = engine
            self.object_index = self._object_index()
        labels = {k: FIELDS[k]["label"] for k in changed}
        reindex = [labels[k] for k in changed if FIELDS[k]["effect"] == REINDEX]
        dense = [labels[k] for k in changed if FIELDS[k]["effect"] == DENSE]
        self.reindex_pending = sorted(set(self.reindex_pending) | set(reindex))
        return {
            "ok": True,
            "changed": [labels[k] for k in changed],
            "reindex_needed": self.reindex_pending,
            "dense_needed": dense,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "status": self.settings_get()["status"],
        }

    def settings_test(self, body: dict[str, Any]) -> dict[str, Any]:
        """Try the (unsaved) model settings from the form: server, chat model, embeddings."""
        endpoint = str(body.get("endpoint") or self.engine.settings.llm.endpoint)
        model = str(body.get("model") or "")
        embed = str(body.get("embedding_model") or "")
        client = OpenAICompatibleClient(
            endpoint,
            model,
            embed,
            temperature=float(body.get("temperature", 0.0)),
            timeout=float(body.get("timeout", 120)),
            api_key=self.engine.settings.llm.api_key,
            reasoning_effort=str(body.get("reasoning_effort", "none")),
        )
        steps: list[dict[str, Any]] = []

        def step(name: str, fn: Any) -> None:
            t0 = time.perf_counter()
            try:
                ok, detail = fn()
            except LLMError as exc:
                ok, detail = False, str(exc)
            steps.append(
                {
                    "name": name,
                    "ok": ok,
                    "detail": detail,
                    "ms": round((time.perf_counter() - t0) * 1000),
                }
            )

        def server() -> tuple[bool, str]:
            ids = client.ping()
            return True, f"{len(ids)} model sunuluyor"

        def chat() -> tuple[bool, str]:
            if not model:
                return False, "Hakem modeli seçilmedi"
            reply = client.chat_json(
                "Kısa ve doğru cevap ver. SADECE JSON döndür.",
                "Türkiye'nin başkenti neresidir?",
                {
                    "type": "object",
                    "properties": {"cevap": {"type": "string"}},
                    "required": ["cevap"],
                    "additionalProperties": False,
                },
                max_tokens=60,
            )
            if reply is None:
                return False, "Geçerli JSON dönmedi (düşünme modu açık olabilir)"
            return True, f"JSON geçerli · cevap: {str(reply.get('cevap', ''))[:40]}"

        def embedding() -> tuple[bool, str]:
            if not embed:
                return False, "Embedding modeli seçilmedi"
            vec = client.embed(["kredi kartı limit doluluk oranı"])[0]
            ok = not self.engine.dense or len(vec) == self.engine.dense.dim
            note = (
                ""
                if ok
                else f" (indeks {self.engine.dense.dim if self.engine.dense else '?'} boyutlu!)"
            )
            return ok, f"{len(vec)} boyutlu vektör{note}"

        step("Sunucu", server)
        if steps[0]["ok"]:
            step("Hakem modeli", chat)
            step("Embedding modeli", embedding)
        return {"steps": steps}

    def reindex(self) -> dict[str, Any]:
        """Rebuild the BM25 index from the dictionary with the saved settings (~10 s)."""
        started = time.perf_counter()
        settings = load_settings(self.settings_path)
        with self.lock:
            fresh = Engine.from_dictionary_file(settings)
            meta = fresh.save()
            self.engine = Engine.from_index(settings)
            self.object_index = self._object_index()
        self.reindex_pending = []
        return {
            "ok": True,
            "columns": meta["columns"],
            "objects": meta["objects"],
            "version": meta["dictionary_version"],
            "dense": self.engine.hybrid,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

    def lab_state(self) -> dict[str, Any]:
        """Model lab results (ranked, best first) and the live progress of a running lab."""
        results: dict[str, Any] = {}
        if self.lab_results.exists():
            results = json.loads(self.lab_results.read_text(encoding="utf-8"))
        errors = {m: c["load_error"]["error"] for m, c in results.items() if "load_error" in c}
        progress: dict[str, Any] = {}
        if self.lab_progress.exists():
            try:
                progress = json.loads(self.lab_progress.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # being rewritten right now
                progress = {"running": True}
        if progress.get("running"):
            proc = self._lab_proc
            if proc is not None and proc.poll() is not None:
                progress["running"] = False  # our child died without cleaning up
            elif time.time() - self.lab_progress.stat().st_mtime > LAB_STALE_SEC:
                progress["running"] = False
        progress["stopping"] = self.lab_stop_flag.exists()
        return {
            "rows": lab.rank(results),
            "errors": errors,
            "progress": progress,
            "weights": {"judge": lab.W_JUDGE, "final": lab.W_FINAL, "picks": lab.W_PICKS,
                        "order": lab.W_ORDER, "drift": lab.W_DRIFT, "tie": lab.TIE},
        }  # fmt: skip

    def lab_start(self, body: dict[str, Any]) -> dict[str, Any]:
        """Run `vsa lab` as a child process; progress is read back from its state file."""
        if self.lab_state()["progress"].get("running"):
            raise ValueError("Bir ölçüm zaten çalışıyor")
        models = [str(m) for m in body.get("models") or []]
        if not models:
            raise ValueError("En az bir model seçin")
        temps = [float(x) for x in str(body.get("temps", "0")).split(",") if x.strip()]
        if not temps or any(not 0 <= x <= 1 for x in temps):
            raise ValueError("Sıcaklıklar 0 ile 1 arasında olmalı")
        runs = int(body.get("runs", 2))
        if not 1 <= runs <= 5:
            raise ValueError("Tekrar sayısı 1 ile 5 arasında olmalı")
        chat = {m["id"] for m in self._lmstudio_models(self.engine.settings.llm.endpoint)
                if m["kind"] == "chat"}  # fmt: skip
        if any(m.startswith(CLOUD_PREFIX) for m in models):
            cloud = self.cloud_models()
            if not cloud["ok"]:
                raise ValueError(cloud["reason"])
            chat |= {m["id"] for m in cloud["models"]}
        unknown = [m for m in models if m not in chat]
        if unknown:
            raise ValueError(f"LM Studio'da bulunmayan model: {', '.join(unknown)}")
        args = [sys.executable, "-m", "vsa.cli", "lab", *models,
                "--temps", ",".join(f"{x:g}" for x in temps), "--runs", str(runs),
                "--settings", str(self.settings_path)]  # fmt: skip
        LAB_LOG.parent.mkdir(parents=True, exist_ok=True)
        self.lab_stop_flag.unlink(missing_ok=True)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "COLUMNS": "160"}
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with LAB_LOG.open("w", encoding="utf-8") as logf:
            self._lab_proc = subprocess.Popen(
                args, stdout=logf, stderr=subprocess.STDOUT, env=env, creationflags=flags
            )
        # Mark as running at once, so a second click cannot start a second lab.
        self.lab_progress.parent.mkdir(parents=True, exist_ok=True)
        self.lab_progress.write_text(json.dumps({
            "running": True, "pid": self._lab_proc.pid, "updated": time.time(),
            "done": 0, "total": 0, "models": models, "log": ["Başlatılıyor…"],
        }, ensure_ascii=False), encoding="utf-8")  # fmt: skip
        return {"ok": True, "pid": self._lab_proc.pid}

    def lab_stop(self) -> dict[str, Any]:
        self.lab_stop_flag.parent.mkdir(parents=True, exist_ok=True)
        self.lab_stop_flag.write_text("stop", encoding="utf-8")
        return {"ok": True}

    def galaxy(self) -> list[dict[str, Any]]:
        """Every object with its main dataset group — the star map of the "Evren" skin."""
        out = []
        for r in self.object_index:
            groups = r["groups"]
            out.append(
                {
                    "key": r["key"],
                    "name": r["name"],
                    "schema": r["schema"],
                    "group": groups[0] if groups else "Diğer",
                    "columns": r["columns"],
                }
            )
        return out

    def object_detail(self, key: str) -> dict[str, Any]:
        obj = self.engine.objects.get(key)
        if obj is None:
            raise KeyError(key)
        first = obj.features[0].col
        return {
            "key": key,
            "name": first.object_name,
            "schema": f"{first.database}.{first.schema}",
            "columns": [serialize.column(f.col) for f in obj.features],
            "join_keys": self.engine.join_keys.get(key, []),
        }

    def feedback(self, body: dict[str, Any]) -> dict[str, Any]:
        vote = str(body.get("vote", ""))
        if vote not in ("up", "down"):
            raise ValueError("vote: up | down")
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "query": str(body.get("query", ""))[:2000],
            "object": str(body.get("object", ""))[:300],
            "field": str(body.get("field", ""))[:300],
            "vote": vote,
            "note": str(body.get("note", ""))[:2000],
            "dictionary_version": self.engine.dictionary.version,
        }
        self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, self.feedback_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"ok": True}


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "VSA/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            log.info("%s %s", self.address_string(), format % args)

        # -------------------------------------------------------------- helpers

        def _send(
            self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _error(self, status: int, message: str) -> None:
            self._json({"error": message}, status)

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                raise ValueError("Dosya çok büyük")
            return self.rfile.read(length) if length else b""

        # -------------------------------------------------------------- routes

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            try:
                if url.path in ("/", "/index.html"):
                    html = (STATIC / "index.html").read_bytes()
                    self._send(200, html, "text/html; charset=utf-8")
                elif url.path in ("/ayarlar", "/settings"):
                    html = (STATIC / "settings.html").read_bytes()
                    self._send(200, html, "text/html; charset=utf-8")
                elif url.path == "/api/settings":
                    self._json(app.settings_get())
                elif url.path == "/api/lab":
                    self._json(app.lab_state())
                elif url.path == "/api/cloud-models":
                    self._json(app.cloud_models(refresh="refresh" in parse_qs(url.query)))
                elif url.path == "/api/status":
                    self._json(app.status())
                elif url.path == "/api/galaxy":
                    self._json(app.galaxy())
                elif url.path.startswith("/api/report/"):
                    path = app.report(url.path.rsplit("/", 1)[-1])
                    name = path.name
                    self._send(
                        200,
                        path.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        {"Content-Disposition": f'attachment; filename="{name}"'},
                    )
                elif url.path == "/api/objects":
                    q = parse_qs(url.query).get("q", [""])[0]
                    self._json(app.objects(q))
                elif url.path.startswith("/api/object/"):
                    self._json(app.object_detail(unquote(url.path.split("/api/object/", 1)[1])))
                else:
                    self._error(404, "Bulunamadı")
            except KeyError:
                self._error(404, "Kayıt bulunamadı")
            except Exception as exc:  # pragma: no cover - last-resort guard
                log.exception("GET %s", self.path)
                self._error(500, f"Sunucu hatası: {exc}")

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            started = time.perf_counter()
            try:
                raw = self._body()
                if url.path == "/api/ask":
                    self._json(app.ask(json.loads(raw or b"{}")))
                elif url.path == "/api/batch":
                    ctype = self.headers.get("Content-Type", "")
                    if ctype.startswith("application/json"):
                        body = json.loads(raw or b"{}")
                        fields = [
                            RequestField(i, str(f.get("tr", "")), str(f.get("en", "")),
                                         str(f.get("description", "")))
                            for i, f in enumerate(body.get("fields", []), 1)
                            if f.get("tr") or f.get("en")
                        ]  # fmt: skip
                        name = str(body.get("name") or "Talep")
                    else:
                        name = unquote(self.headers.get("X-Filename", "talep.xlsx"))
                        with tempfile.TemporaryDirectory() as tmp:
                            path = Path(tmp) / "request.xlsx"
                            path.write_bytes(raw)
                            fields = load_request_file(path)
                        name = Path(name).stem
                    self._json(app.batch(fields, name))
                elif url.path == "/api/settings":
                    self._json(app.settings_save(json.loads(raw or b"{}")))
                elif url.path == "/api/settings/test":
                    self._json(app.settings_test(json.loads(raw or b"{}")))
                elif url.path == "/api/reindex":
                    self._json(app.reindex())
                elif url.path == "/api/lab/start":
                    self._json(app.lab_start(json.loads(raw or b"{}")))
                elif url.path == "/api/lab/stop":
                    self._json(app.lab_stop())
                elif url.path == "/api/feedback":
                    self._json(app.feedback(json.loads(raw or b"{}")))
                else:
                    self._error(404, "Bulunamadı")
            except (ValueError, json.JSONDecodeError) as exc:
                self._error(400, str(exc))
            except Exception as exc:
                log.exception("POST %s", self.path)
                self._error(500, f"Sunucu hatası: {exc}")
            finally:
                log.info("POST %s %.1fs", url.path, time.perf_counter() - started)

    return Handler


def serve(
    engine: Engine,
    host: str,
    port: int,
    out_dir: Path,
    feedback_path: Path,
    settings_path: Path | None = None,
) -> None:
    app = App(engine, out_dir, feedback_path, settings_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    log.warning("VSA arayüzü: http://%s:%d", host, port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
