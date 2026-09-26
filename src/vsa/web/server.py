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
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from vsa.batch import BatchAnalyzer
from vsa.loader import load_request_file
from vsa.models import AnalysisResult, BatchResult, RequestField
from vsa.pipeline import Engine
from vsa.report.excel import report_path, write_ask_report, write_batch_report
from vsa.text.normalize import fold
from vsa.web import serialize

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 20 * 1024 * 1024
MAX_REPORTS = 50
EXPLORER_LIMIT = 60
EXPLORER_CONTENT_LIMIT = 25  # objects from the content (search pipeline) layer
MIN_CONTENT_QUERY = 3  # shorter input: name matching only


class App:
    def __init__(self, engine: Engine, out_dir: Path, feedback_path: Path) -> None:
        self.engine = engine
        self.out_dir = out_dir
        self.feedback_path = feedback_path
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
            with self.lock:
                ranked, eq = self.engine.rank_objects(
                    text, use_llm=False, limit=EXPLORER_CONTENT_LIMIT
                )
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


def serve(engine: Engine, host: str, port: int, out_dir: Path, feedback_path: Path) -> None:
    app = App(engine, out_dir, feedback_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    log.warning("VSA arayüzü: http://%s:%d", host, port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
