"""Web server (M6). Standard library only — nothing extra to ship into a closed network.
One engine, one lock: the tool serves a team, not the internet. Who may reach the admin
screen, CSRF and response headers: ``vsa.web.security``. TLS is the reverse proxy's job.

    GET  /                      single-page UI (static/index.html, no external assets)
    GET  /healthz               liveness for the container (no model call)
    GET  /api/status            dictionary / search / LLM status
    POST /api/ask               {"query": "...", "top": 5, "ask_id": "...", "fresh": false};
                                an earlier analyst answer to the same question (or one meaning
                                the same) is given again unless "fresh" (ADR-035)
    POST /api/ask/cancel        {"ask_id": "..."} stop that analysis and its LLM calls
    POST /api/list              raw .xlsx body (X-Filename): a term list, one per row of the
                                first column, each answered by the question flow (ADR-033)
    GET  /api/list              the latest list (to reattach after a page reload)
    GET  /api/list/<id>         progress: every term's state and short answer
    GET  /api/list/<id>/item/<n>  one term's full answer (as /api/ask returns it)
    POST /api/list/<id>/cancel  stop the list (the running term's LLM calls too)
    POST /api/list/<id>/resume  go on with a stopped list; answered terms are kept
    GET  /api/list/<id>/report  one Excel report for the whole list (also while running)
    GET  /api/report/<id>       Excel report of an earlier question
    GET  /api/objects?q=...     dictionary explorer: objects matching a name
    GET  /api/object/<key>      all columns of one object
    GET  /api/galaxy            all objects with their dataset group (star map)
    POST /api/feedback          {"query", "object" | "scope": "answer", "vote": "up"|"down",
                                "note", "voter"}: kept; later answers weigh them (ADR-036)
    GET  /admin                 admin screen (static/admin.html): analyses + settings;
                                no link from the app, reached by typing the address;
                                it and every /api/admin, /api/settings, /api/reindex and
                                /api/llm route pass ``AdminGuard`` (password or this machine)
    GET  /api/admin/analyses    recent analyses: who asked what, flow, steps' durations
    POST /api/admin/analyses/clear  {"ids": [...]} or {"all": true}: delete records
                                for good (no backup)
    POST /api/admin/answers/clear  forget every kept answer (ADR-035)
    GET  /api/admin/analysis/<id>  one analysis with its full step timeline (trace spans)
    GET  /api/admin/dictionary  the dictionary (ADR-049/050): meta and every table
    GET  /api/admin/dictionary/table/<key>  one table of the store: object + column records
    GET  /api/admin/dictionary/export    the store as a workbook in the dictionary template
    GET  /api/admin/dictionary/template  the empty template
    POST /api/admin/dictionary/import    raw .xlsx body (X-Filename) in the template becomes
                                the dictionary; the index is rebuilt
    GET  /api/admin/words       term dictionary and stopwords as the screen edits them
    POST /api/admin/words/terms     {"items": [{term, equivalents, domain, note}]} replaces
    POST /api/admin/words/stopwords {"items": [{word, group}]} the list; index rebuilt (ADR-052)
    GET  /api/admin/words/<terms|stopwords>/export   one list as Excel
    POST /api/admin/words/<terms|stopwords>/import   that Excel (edited) replaces the list
    GET  /api/settings          pages, sections and current values (search, scoring, files)
    POST /api/settings          {"values": {...}} validate, write data/settings.yaml, reload
    POST /api/reindex           rebuild the BM25 index with the saved settings
    GET  /api/llm               LLM integrations, which one holds the chat role
    GET  /api/llm/inventory     every integration's models, servers asked in parallel
    POST /api/llm/save          {id?, name, endpoint, api_key?, chat_model, …}
    POST /api/llm/activate      {id, enabled, replace?} — one active chat model
    POST /api/llm/delete        {id}
    POST /api/llm/models        {id? | endpoint, api_key} model list of one server (form)
    POST /api/llm/test          {id? + form values, record?} server / chat steps
"""

from __future__ import annotations

import json
import logging
import socket
import tempfile
import threading
import time
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from vsa import answer_cache, cancel, dictionary_store, trace
from vsa import feedback as fb
from vsa.config import load_settings
from vsa.config import settings_path as resolve_settings_path
from vsa.loader import (
    WORD_SHEETS,
    check_stopwords,
    check_terms,
    load_term_list,
    read_stopwords,
    read_terms,
    words_from_workbook,
    words_to_workbook,
    write_jsonl,
)
from vsa.models import AnalysisResult, ListItem, ListResult
from vsa.pipeline import Engine
from vsa.report.excel import report_path, write_ask_report, write_list_report
from vsa.text.normalize import fold
from vsa.web import serialize
from vsa.web.answer_store import AnswerStore
from vsa.web.llm_admin import LLMAdmin
from vsa.web.security import (
    API_CSP,
    BASE_HEADERS,
    REALM,
    AdminGuard,
    cross_site,
    is_admin_path,
    page_csp,
)
from vsa.web.settings_schema import (
    FIELDS,
    PAGES,
    REINDEX,
    SECTIONS,
    coerce,
    defaults,
    to_yaml_tree,
    values_of,
)

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 20 * 1024 * 1024
MAX_QUERY_CHARS = 4000  # a question, not a document; longer text only slows the model
REQUEST_TIMEOUT = 120  # seconds a client may take to send its request (slow-client guard)
MAX_REPORTS = 50
EXPLORER_LIMIT = 60
EXPLORER_CONTENT_LIMIT = 25  # objects from the content (search pipeline) layer
MIN_CONTENT_QUERY = 3  # shorter input: name matching only
LLM_POSTS = {"save": "save", "activate": "set_active", "delete": "delete",
             "models": "models", "test": "test"}  # fmt: skip
ANALYSES_LOG = "logs/analyses.jsonl"  # next to the feedback file (data/)
ANSWERS_FILE = "cache/answers.jsonl"  # kept analyst answers (ADR-035)
ADMIN_LIST_LIMIT = 3000  # newest analyses the admin screen loads
MAX_LISTS = 5  # finished term lists kept for their reports


def _line_id(line: str) -> str:
    try:
        return str(json.loads(line).get("id", ""))
    except (json.JSONDecodeError, AttributeError):
        return ""


class ListJob:
    """A term list being answered in the background, one term at a time (ADR-033)."""

    def __init__(self, name: str, terms: list[str], engine: Engine) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.result = ListResult(
            name=name,
            items=[ListItem(i, t) for i, t in enumerate(terms, 1)],
            dictionary_source=Path(engine.dictionary.source_path).name,
            dictionary_version=engine.dictionary.version,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        self.token = cancel.Token()
        self.current = 0  # index of the term being answered; 0 = none
        self.running = True
        self.started = time.perf_counter()
        self.finished: float | None = None

    def state(self, item: ListItem) -> str:
        if item.result is not None:
            return "bitti"
        if item.error:
            return "hata"
        if item.index == self.current:
            return "çalışıyor"
        return "durduruldu" if self.token.cancelled else "sırada"

    def snapshot(self) -> dict[str, Any]:
        items = self.result.items
        done = [i for i in items if i.result is not None or i.error]
        left = len(items) - len(done)
        mean = sum(i.elapsed_ms for i in done) / len(done) if done else 0
        return {
            "id": self.id,
            "name": self.result.name,
            "header": self.result.header,
            "notes": self.result.notes,
            "running": self.running,
            "cancelled": self.token.cancelled,
            "total": len(items),
            "done": len(done),
            "current": self.current,
            "elapsed_ms": round(((self.finished or time.perf_counter()) - self.started) * 1000),
            "eta_ms": round(mean * left) if self.running and done else None,
            "items": [serialize.list_item(i, self.state(i)) for i in items],
        }


class App:
    def __init__(
        self,
        engine: Engine,
        out_dir: Path,
        feedback_path: Path,
        settings_path: Path | None = None,
        analyses_path: Path | None = None,
    ) -> None:
        self.engine = engine
        self.out_dir = out_dir
        self.feedback_path = feedback_path
        self.analyses_path = analyses_path or feedback_path.parent / ANALYSES_LOG
        self.answers = AnswerStore(feedback_path.parent / ANSWERS_FILE)  # ADR-035
        self._log_lock = threading.Lock()
        self._hosts: dict[str, str] = {}
        self._running: dict[str, cancel.Token] = {}  # ask_id -> token of a running question
        self.settings_path = resolve_settings_path(settings_path)
        self.reindex_pending: list[str] = []
        self.lock = threading.Lock()
        self.results: dict[str, AnalysisResult] = {}
        self.lists: dict[str, ListJob] = {}
        self.object_index = self._object_index()
        self.llm_admin = LLMAdmin(self)

    def reload(self) -> None:
        """Rebuild the engine from the saved settings (and LLM integrations). Built
        outside the engine lock: a question being answered (minutes with the analyst)
        finishes on the old engine instead of holding the change back; the swap is one
        assignment."""
        engine = Engine.from_index(load_settings(self.settings_path))
        self.engine = engine
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

    def _remember(self, result: AnalysisResult) -> str:
        rid = uuid.uuid4().hex[:12]
        self.results[rid] = result
        while len(self.results) > MAX_REPORTS:
            self.results.pop(next(iter(self.results)))
        return rid

    # ------------------------------------------------------------------ endpoints

    def status(self) -> dict[str, Any]:
        e = self.engine
        s = e.settings
        source = Path(e.dictionary.source_path)
        return {
            "dictionary": source.name,
            "version": e.dictionary.version,
            # when the dictionary file was last changed ("" if the index outlived the file)
            "updated": (datetime.fromtimestamp(source.stat().st_mtime).date().isoformat()
                        if source.is_file() else ""),
            "columns": len(e.dictionary.columns),
            "objects": len(e.objects),
            "llm": e.llm.model if e.analyst_enabled else "",
            "analyst": e.analyst_enabled,  # ADR-029: the model writes the answer
            # ADR-034: "ok" | "none" (no chat model) | "down" (configured, not answering)
            "llm_state": self._llm_state(),
            "shortlist": s.analyst.shortlist,
            "examples": [
                "Kredi kartı limit doluluk oranı verisine ihtiyacımız var, nerede?",
                "Müşterilerin risk bilgilerini aylık bazda ve kırılımlı olarak (kredi kartı, "
                "gayrimenkul, ihtiyaç kredisi vb.) gösteren bir tablo mevcut mudur?",
                "Müşteri bazında aylık FAST ve havale transfer adedi ile tutarı",
                "İhtiyaç kredisi kullanan müşterilerin gecikme gün sayısı",
            ],
        }

    def _llm_state(self) -> dict[str, str]:
        e = self.engine
        if not e.analyst_enabled:
            return {"state": "none", "model": "", "reason": e.llm.health()}
        reason = e.llm.health()  # a quick /models call, cached for 30 s
        return {"state": "down" if reason else "ok", "model": e.llm.model, "reason": reason}

    def ask(self, body: dict[str, Any], client: str = "") -> dict[str, Any]:
        query = str(body.get("query", "")).strip()
        if not query:
            raise ValueError("Talep metni boş")
        if len(query) > MAX_QUERY_CHARS:
            raise ValueError(f"Talep çok uzun (en fazla {MAX_QUERY_CHARS} karakter)")
        top = max(1, min(10, int(body.get("top", 5))))
        ask_id = str(body.get("ask_id") or uuid.uuid4().hex)[:64]
        token = cancel.Token()
        self._running[ask_id] = token
        try:
            result, error = self._answer(query, top, client, token, fresh=body.get("fresh") is True)
        finally:
            self._running.pop(ask_id, None)
        if token.cancelled:
            return {"cancelled": True, "ask_id": ask_id}
        if result is None:
            raise RuntimeError(error)
        data = serialize.analysis(result)
        data["report_id"] = self._remember(result)
        voter = str(body.get("voter", "")) or client
        return self._with_feedback(data, voter, result.generated_at)

    def _answer(
        self,
        query: str,
        top: int,
        client: str,
        token: cancel.Token,
        origin: str = "",
        fresh: bool = False,
    ) -> tuple[AnalysisResult | None, str]:
        """The one question flow, for a single question and for every term of a list:
        an earlier answer to the same question when there is one (ADR-035), otherwise
        wait for the engine (stoppable) and answer; log the steps for the admin screen.
        ``fresh`` skips the earlier answer (the user asked for a new analysis)."""
        result: AnalysisResult | None = None
        error = ""
        with trace.recording() as tr, cancel.using(token):
            try:
                engine = self.engine
                keys = engine.cache_keys(query)
                fp = engine.cache_fingerprint(top)
                result = None if fresh else self._reuse(engine, query, keys, fp)
                if result is None:
                    with trace.span("Sırada bekleme", "önceki analizin bitmesi"):
                        while not self.lock.acquire(timeout=0.25):
                            cancel.check()  # stopped while still in the queue
                    try:
                        result = self.engine.analyze(query, top_n=top)
                    finally:
                        self.lock.release()
                    # Only the analyst's answers are worth keeping: a rule answer takes
                    # seconds, and a fallback must not stand in once the model is back.
                    if result.analyst and self.engine is engine:
                        self.answers.put(query, *keys, fp, answer_cache.encode(result))
            except cancel.Cancelled:
                error = "Kullanıcı durdurdu"
                trace.event("Durduruldu", "kullanıcı analizi durdurdu", status="error")
            except Exception as exc:
                log.exception("Analiz başarısız: %s", query[:80])
                error = str(exc) or type(exc).__name__
            finally:
                self._log_analysis(tr, query, client, result, error, token.cancelled, origin)
        return result, error

    def _reuse(
        self, engine: Engine, query: str, keys: tuple[str, str], fp: str
    ) -> AnalysisResult | None:
        """An earlier answer to this question, or to one meaning the same (ADR-035)."""
        c = engine.settings.cache
        if not c.enabled:
            return None
        started = time.perf_counter()
        result: AnalysisResult | None = None
        with trace.span("Önceki cevap araması") as sp:
            hit = self.answers.lookup(
                *keys, fp, use_meaning=c.meaning, max_age_days=c.max_age_days
            )
            if hit is not None:
                result = answer_cache.decode(hit.entry["result"], engine.dictionary.by_key())
            if sp is not None:
                sp.detail = f"{hit.match}: {hit.entry['query'][:120]}" if hit and result else "yok"
        if hit is None or result is None:
            return None
        at = datetime.fromisoformat(hit.entry["at"]).strftime("%d.%m.%Y %H:%M")
        first = "Bu soru" if hit.match == "aynı soru" else (
            f"Aynı anlama gelen “{hit.entry['query']}” sorusu")  # fmt: skip
        result.method = [
            f"{first} {at} tarihinde analiz edildi ({result.elapsed_ms / 1000:.0f} sn); kayıtlı "
            "cevap yeniden kullanıldı (sözlük, model ve ayarlar aynı). Yeni bir analiz için "
            "“Yeniden analiz et”.",
            *result.method,
        ]
        result.reused_at, result.reused_match = at, hit.match
        result.reused_query = hit.entry["query"]
        result.query = query
        result.elapsed_ms = round((time.perf_counter() - started) * 1000)
        return result

    # ------------------------------------------------------------------ term lists (ADR-033)

    def list_start(self, raw: bytes, filename: str, client: str = "") -> dict[str, Any]:
        if any(j.running for j in self.lists.values()):
            raise ValueError("Bir liste zaten çalışıyor; bitmesini bekleyin ya da durdurun.")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "liste.xlsx"
            path.write_bytes(raw)
            read = load_term_list(path)  # ValueError in Turkish for anything it cannot read
        job = ListJob(Path(filename).name or "liste.xlsx", read.terms, self.engine)
        job.result.header, job.result.notes = read.header, read.notes
        self.lists[job.id] = job
        for old in [k for k, j in self.lists.items() if not j.running][:-MAX_LISTS]:
            self.lists.pop(old)
        threading.Thread(target=self._run_list, args=(job, client), daemon=True).start()
        return job.snapshot()

    def _run_list(self, job: ListJob, client: str) -> None:
        try:
            for item in job.result.items:
                if job.token.cancelled:
                    break
                if item.result is not None:  # answered before a stop: resuming skips it
                    continue
                item.error = ""
                job.current = item.index
                t0 = time.perf_counter()
                origin = f"{job.result.name} #{item.index}"
                result, error = self._answer(item.term, 5, client, job.token, origin)
                if job.token.cancelled and result is None:
                    break  # the stopped term stays unanswered, not an error
                item.result, item.error = result, error
                item.elapsed_ms = round((time.perf_counter() - t0) * 1000)
        finally:
            job.current = 0
            job.finished = time.perf_counter()
            job.running = False
            job.result.cancelled = job.token.cancelled

    def list_job(self, jid: str) -> ListJob:
        job = self.lists.get(jid)
        if job is None:
            raise KeyError(jid)
        return job

    def list_latest(self) -> dict[str, Any]:
        jobs = list(self.lists.values())
        return jobs[-1].snapshot() if jobs else {}

    def list_item(self, jid: str, index: int, voter: str = "") -> dict[str, Any]:
        items = self.list_job(jid).result.items
        result = items[index - 1].result if 1 <= index <= len(items) else None
        if result is None:
            raise KeyError(index)
        data = serialize.analysis(result)
        data["report_id"] = self._remember(result)
        return self._with_feedback(data, voter, result.generated_at)

    def list_cancel(self, jid: str) -> dict[str, Any]:
        job = self.list_job(jid)
        job.token.cancel()
        return job.snapshot()

    def list_resume(self, jid: str, client: str = "") -> dict[str, Any]:
        """Go on with a stopped list from where it stopped: answered terms are kept, the
        rest (and any that failed) are asked again. The pause does not count as run time."""
        job = self.list_job(jid)
        if job.running:
            return job.snapshot()
        if any(j.running for j in self.lists.values()):
            raise ValueError("Bir liste zaten çalışıyor; bitmesini bekleyin ya da durdurun.")
        if all(i.result is not None for i in job.result.items):
            raise ValueError("Bu listenin bütün terimleri cevaplandı; devam edecek terim yok.")
        if job.finished is not None:
            job.started += time.perf_counter() - job.finished
        job.token, job.running, job.finished = cancel.Token(), True, None
        job.result.cancelled = False
        threading.Thread(target=self._run_list, args=(job, client), daemon=True).start()
        return job.snapshot()

    def list_report(self, jid: str) -> Path:
        r = self.list_job(jid).result
        r.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        return write_list_report(r, report_path(self.out_dir, "liste", Path(r.name).stem))

    def cancel_ask(self, body: dict[str, Any]) -> dict[str, Any]:
        """Stop a running question: its waits end and its LLM connections are cut."""
        token = self._running.get(str(body.get("ask_id", "")))
        if token is not None:
            token.cancel()
        return {"ok": token is not None}

    # ------------------------------------------------------------------ admin: analyses

    def _host(self, ip: str) -> str:
        """Machine name of a client (reverse DNS, cached); "" when it has none."""
        if ip not in self._hosts:
            try:
                name = socket.gethostname() if ip in ("127.0.0.1", "::1") else (
                    socket.gethostbyaddr(ip)[0])  # fmt: skip
            except OSError:
                name = ""
            self._hosts[ip] = name
        return self._hosts[ip]

    def _log_analysis(
        self,
        tr: trace.Trace,
        query: str,
        ip: str,
        result: AnalysisResult | None,
        error: str,
        stopped: bool = False,
        origin: str = "",
    ) -> None:
        """One line per question in data/logs/analyses.jsonl: who, what, the path it took."""
        spans = tr.to_list()
        if stopped:
            flow = "durduruldu"
        elif result is None:
            flow = "hata"
        elif result.reused_at:
            flow = "önbellek"  # an earlier analyst answer given again (ADR-035)
        else:
            flow = "analist" if result.analyst else "yapılamadı"  # ADR-038: no rule answers
        entry = {
            "id": uuid.uuid4().hex[:12],
            "at": datetime.now().isoformat(timespec="seconds"),
            "ip": ip,
            "host": self._host(ip) if ip else "",
            "query": query[:2000],
            "origin": origin,  # "liste.xlsx #3" for a term of a list (ADR-033)
            "flow": flow,
            "model": self.engine.llm.model if flow in ("analist", "yapılamadı", "durduruldu") else (
                result.llm_model if result else ""),  # fmt: skip
            "verdict": result.verdict.value if result else "",
            "summary": result.summary[:500] if result else "",
            "objects": [m.object_key for m in result.objects][:10] if result else [],
            "fallback": result.fallback if result else "",
            "reused": serialize.reused(result) if result else None,
            "error": error[:500],
            "ms": round(tr.now() * 1000),
            **tr.totals(),
            "dictionary_version": self.engine.dictionary.version,
            "spans": spans,
        }
        try:
            self.analyses_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_lock, self.analyses_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:  # the answer matters more than its log line
            log.warning("Analiz kaydı yazılamadı: %s", exc)

    def _analysis_lines(self) -> list[dict[str, Any]]:
        if not self.analyses_path.is_file():
            return []
        with self._log_lock:
            lines = self.analyses_path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-ADMIN_LIST_LIMIT:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a line cut short by a crash
        return out

    def analyses(self) -> dict[str, Any]:
        """Recent analyses, newest first, without their timelines; each carries the time
        spent per step so the screen can add them up."""
        items = []
        for e in reversed(self._analysis_lines()):
            spans = e.pop("spans", [])
            steps: dict[str, int] = {}
            for sp in spans:
                if sp["kind"] == trace.STEP and not sp["name"].startswith("Parça"):
                    steps[sp["name"]] = steps.get(sp["name"], 0) + int(sp["ms"])
            e["steps"] = steps
            e["waits"] = sum(int(sp["ms"]) for sp in spans if sp["kind"] == trace.EVENT)
            items.append(e)
        return {"items": items, "path": str(self.analyses_path), "limit": ADMIN_LIST_LIMIT}

    def clear_analyses(self, body: dict[str, Any]) -> dict[str, Any]:
        """Delete the given analyses, or all of them with ``{"all": true}`` — never by
        omission. Deleted records are gone; no backup is kept."""
        everything = body.get("all") is True
        ids = {str(i) for i in body.get("ids") or []}
        if not everything and not ids:
            raise ValueError("Silinecek analiz seçilmedi")
        if not self.analyses_path.is_file():
            return {"removed": 0, "kept": 0}
        with self._log_lock:
            lines = self.analyses_path.read_text(encoding="utf-8").splitlines()
            kept = [] if everything else [ln for ln in lines if _line_id(ln) not in ids]
            self.analyses_path.write_text("".join(f"{ln}\n" for ln in kept), encoding="utf-8")
        return {"removed": len(lines) - len(kept), "kept": len(kept)}

    def clear_answers(self) -> dict[str, Any]:
        """Forget every kept answer (ADR-035); the next questions are analysed anew."""
        return {"removed": self.answers.clear()}

    def analysis(self, aid: str) -> dict[str, Any]:
        for e in self._analysis_lines():
            if e.get("id") == aid:
                return e
        raise KeyError(aid)

    def report(self, rid: str) -> Path:
        result = self.results.get(rid)
        if result is None:
            raise KeyError(rid)
        return write_ask_report(result, report_path(self.out_dir, "ask", result.query))

    def objects(self, q: str) -> dict[str, Any]:
        """Explorer search: every search layer except the chat model.

        1. name — table / schema / dataset group contains the text (instant, listed first)
        2. content — the full pipeline without the LLM: Turkish normalization, term
           dictionary, dictionary synonyms, BM25 and object aggregation;
           finds tables by their column names and descriptions, not only by their names
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
            # prefetch — stay instant while an analyst question holds the lock.
            ranked, eq = self.engine.rank_objects(text, limit=EXPLORER_CONTENT_LIMIT)
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
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

    # ------------------------------------------------------------------ settings screen

    def settings_get(self) -> dict[str, Any]:
        st = self.engine.settings
        return {
            "pages": PAGES,
            "sections": SECTIONS,
            "values": values_of(st),
            "defaults": defaults(),
            "path": str(self.settings_path),
            "status": {
                "llm": self.engine.llm.available,
                "llm_model": self.engine.llm.model,
                "dictionary_version": self.engine.dictionary.version,
                "index_built_at": self.engine.index_meta.get("built_at", ""),
                "answers": self.answers.stats(self.engine.cache_fingerprint(5)),  # ADR-035
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
        changed = [k for k in FIELDS if new[k] != current[k]]

        self._write_settings(to_yaml_tree(new, self._settings_tree()))
        self.reload()
        labels = {k: FIELDS[k]["label"] for k in changed}
        reindex = [labels[k] for k in changed if FIELDS[k]["effect"] == REINDEX]
        self.reindex_pending = sorted(set(self.reindex_pending) | set(reindex))
        return {
            "ok": True,
            "changed": [labels[k] for k in changed],
            "reindex_needed": self.reindex_pending,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "status": self.settings_get()["status"],
        }

    def _settings_tree(self) -> dict[str, Any]:
        """The settings file as it is (keys the screens do not show survive a save)."""
        if not self.settings_path.exists():
            return {}
        data = yaml.safe_load(self.settings_path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}

    def _write_settings(self, tree: dict[str, Any]) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# DWH Navigator ayarları — Yönetim ekranından kaydedildi "
            f"({datetime.now().isoformat(timespec='seconds')}).\n"
            "# Elle de düzenlenebilir; anlamları için: docs/settings.example.yaml\n"
        )
        self.settings_path.write_text(
            header + yaml.safe_dump(tree, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    # ------------------------------------------------------------------ dictionary (ADR-049)

    def _store_path(self) -> Path:
        return Path(self.engine.settings.dictionary.store)

    def dictionary_state(self) -> dict[str, Any]:
        store = self._store_path()
        state: dict[str, Any] = {
            "store": {"path": self.engine.settings.dictionary.store, "exists": store.is_file()},
            "active_version": self.engine.dictionary.version,
            "summary": None,
            "error": "",
        }
        if store.is_file():
            try:
                state["summary"] = dictionary_store.summary(store)
            except (OSError, ValueError) as exc:
                state["error"] = str(exc)
        return state

    def dictionary_table(self, key: str) -> dict[str, Any]:
        return dictionary_store.table(self._store_path(), key)

    def dictionary_import(self, raw: bytes, filename: str) -> dict[str, Any]:
        """A workbook in the template becomes the dictionary; the index is rebuilt at once."""
        started = time.perf_counter()
        if not raw:
            raise ValueError("Dosya boş")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sozluk.xlsx"
            path.write_bytes(raw)
            store = dictionary_store.from_workbook(path, Path(filename).name or "sozluk.xlsx")
        dictionary_store.save(store, self._store_path())
        self.reindex()
        return {
            "ok": True,
            "meta": store.meta,
            "warnings": store.warnings[:20],
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "state": self.dictionary_state(),
        }

    def dictionary_export(self, template: bool = False) -> tuple[str, bytes]:
        """(file name, workbook bytes): the store, or the empty template."""
        store = None if template else dictionary_store.read(self._store_path())
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        name = "VeriSozlugu_sablon.xlsx" if template else f"VeriSozlugu_{stamp}.xlsx"
        with tempfile.TemporaryDirectory() as tmp:
            path = dictionary_store.export(store, Path(tmp) / name)
            return name, path.read_bytes()

    def _word_paths(self) -> dict[str, Path]:
        e = self.engine.settings.expansion
        return {"terms": Path(e.term_dictionary), "stopwords": Path(e.stopwords)}

    def words_state(self) -> dict[str, Any]:
        paths = self._word_paths()
        return {
            "terms": {"path": paths["terms"].as_posix(), "items": read_terms(paths["terms"])},
            "stopwords": {
                "path": paths["stopwords"].as_posix(),
                "items": read_stopwords(paths["stopwords"]),
            },
        }

    def words_save(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        """Replace one word list; both are in the index (BM25), so it is rebuilt at once.
        Answers kept under the old term dictionary stop matching by themselves (ADR-035)."""
        started = time.perf_counter()
        if kind not in WORD_SHEETS:
            raise KeyError(kind)
        rows = (check_terms if kind == "terms" else check_stopwords)(body.get("items"))
        write_jsonl(self._word_paths()[kind], rows)
        self.reindex()
        return {
            "ok": True,
            "count": len(rows),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "state": self.words_state(),
        }

    def words_export(self, kind: str) -> tuple[str, bytes]:
        """(file name, workbook bytes): one word list as the screen shows it."""
        if kind not in WORD_SHEETS:
            raise KeyError(kind)
        items = self.words_state()[kind]["items"]
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        name = f"{'TerimSozlugu' if kind == 'terms' else 'DurakKelimeler'}_{stamp}.xlsx"
        with tempfile.TemporaryDirectory() as tmp:
            return name, words_to_workbook(kind, items, Path(tmp) / name).read_bytes()

    def words_import(self, kind: str, raw: bytes) -> dict[str, Any]:
        """An exported (maybe edited) workbook replaces the list, checked like a save."""
        if kind not in WORD_SHEETS:
            raise KeyError(kind)
        if not raw:
            raise ValueError("Dosya boş")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "liste.xlsx"
            path.write_bytes(raw)
            items = words_from_workbook(kind, path)
        return self.words_save(kind, {"items": items})

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
            "groups": sorted({f.col.dataset_group for f in obj.features if f.col.dataset_group}),
            "columns": [serialize.column(f.col) for f in obj.features],
            "join_keys": self.engine.join_keys.get(key, []),
        }

    # ------------------------------------------------------------------ feedback (ADR-036)

    def feedback(self, body: dict[str, Any], client: str = "") -> dict[str, Any]:
        """One 👍/👎 on a suggested table, or on the whole answer (``scope: answer``).
        Every person's latest vote counts; enough 👎 on the answer drop its kept copy,
        so the next asker gets a fresh analysis (ADR-035/036)."""
        vote = str(body.get("vote", ""))
        if vote not in ("up", "down"):
            raise ValueError("vote: up | down")
        scope = "answer" if body.get("scope") == "answer" else "object"
        query = str(body.get("query", "")).strip()[:2000]
        engine = self.engine
        text, meaning = engine.cache_keys(query) if query else ("", "")
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "query": query,
            "text_key": text,
            "meaning_key": meaning,
            "scope": scope,
            "object": "" if scope == "answer" else str(body.get("object", ""))[:300],
            "vote": vote,
            "note": str(body.get("note", ""))[:2000],
            "voter": str(body.get("voter", ""))[:64] or client,
            "rank": body.get("rank"),
            "score": body.get("score"),
            "analyst": bool(body.get("analyst")),
            "reused": bool(body.get("reused")),
            "report_id": str(body.get("report_id", ""))[:64],
            "dictionary_version": engine.dictionary.version,
        }
        self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
        with _feedback_lock, self.feedback_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        view = self._feedback_view(
            text, meaning, str(entry["voter"]), str(body.get("answer_at", ""))
        )
        dropped = 0
        if scope == "answer" and view.answer_rejected:
            dropped = self.answers.forget(text, meaning)
        tally = view.answer if scope == "answer" else view.objects.get(str(entry["object"]))
        return {
            "ok": True,
            "votes": tally.to_dict() if tally else None,
            "answer_rejected": view.answer_rejected,
            "forgotten": dropped,
        }

    def _feedback_view(
        self, text: str, meaning: str, voter: str, answer_at: str = ""
    ) -> fb.FeedbackView:
        with _feedback_lock:
            rows = fb.load_feedback(self.feedback_path)
        for r in rows:  # votes from before ADR-036 carry the question only
            if "text_key" not in r:
                r["text_key"] = answer_cache.text_key(str(r.get("query", "")))
        version = self.engine.dictionary.version
        return fb.assess(
            rows, text, meaning, dictionary_version=version, voter=voter, answer_since=answer_at
        )

    def _with_feedback(self, data: dict[str, Any], voter: str, answer_at: str) -> dict[str, Any]:
        """The answer as earlier votes on this question shape it (ADR-036)."""
        try:
            keys = self.engine.cache_keys(data["query"])
            out = fb.apply(data, self._feedback_view(*keys, voter, answer_at), self._known())
        except Exception:  # votes must never cost the answer
            log.exception("Geri bildirim değerlendirilemedi")
            return data
        out["feedback"]["answer_at"] = answer_at  # echoed back with a vote on the answer
        return out

    def _known(self) -> dict[str, dict[str, Any]]:
        return {r["key"]: {"name": r["name"], "schema": r["schema"], "groups": r["groups"]}
                for r in self.object_index}  # fmt: skip


_feedback_lock = threading.Lock()  # not the engine lock: a vote must not wait for an analysis


class _Refused(Exception):
    """A request the policy turns away (status, Turkish message, extra headers)."""

    def __init__(self, status: int, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status, self.message, self.headers = status, message, headers or {}


def _json_body(raw: bytes) -> dict[str, Any]:
    try:
        text = (raw or b"{}").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("İstek gövdesi UTF-8 değil") from exc
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("JSON nesnesi bekleniyor")
    return data


def make_handler(app: App, guard: AdminGuard | None = None) -> type[BaseHTTPRequestHandler]:
    admin = guard or AdminGuard()
    pages = {name: (STATIC / name).read_bytes() for name in ("index.html", "admin.html")}
    csp = {name: page_csp(html) for name, html in pages.items()}

    class Handler(BaseHTTPRequestHandler):
        timeout = REQUEST_TIMEOUT

        def version_string(self) -> str:
            return "VSA"  # no server or Python version in the Server header

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            log.info("%s %s", self.address_string(), format % args)

        # -------------------------------------------------------------- helpers

        def _send(
            self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            headers = {**BASE_HEADERS, "Content-Security-Policy": API_CSP, **(extra or {})}
            for k, v in headers.items():
                self.send_header(k, v)
            try:
                self.end_headers()
                self.wfile.write(body)
            except ConnectionError:  # the browser left (e.g. the question was stopped)
                self.close_connection = True

        def _json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _xlsx(self, path: Path) -> None:
            self._xlsx_bytes(path.name, path.read_bytes())

        def _xlsx_bytes(self, name: str, data: bytes) -> None:
            self._send(
                200,
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                {"Content-Disposition": f'attachment; filename="{name}"'},
            )

        def _error(self, status: int, message: str, extra: dict[str, str] | None = None) -> None:
            body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8", extra)

        def send_error(
            self, code: int, message: str | None = None, explain: str | None = None
        ) -> None:
            """``http.server``'s own errors (bad request line, unsupported method…) as JSON
            with the same security headers as every other response."""
            self.close_connection = True
            self._error(code, message or HTTPStatus(code).phrase)

        def _page(self, name: str) -> None:
            extra = {"Content-Security-Policy": csp[name]}
            self._send(200, pages[name], "text/html; charset=utf-8", extra)

        def _body(self) -> bytes:
            if self.headers.get("Transfer-Encoding"):
                raise _Refused(411, "Content-Length gerekli")
            raw = (self.headers.get("Content-Length") or "0").strip()
            if not raw.isdigit():
                raise _Refused(400, "Geçersiz Content-Length")
            length = int(raw)
            if length > MAX_UPLOAD:
                raise _Refused(413, "Dosya çok büyük (en fazla 20 MB)")
            return self.rfile.read(length) if length else b""

        def _guard(self, path: str, post: bool = False) -> None:
            """Raise ``_Refused`` for a request the policy turns away."""
            if post and cross_site(self.headers):
                raise _Refused(403, "Başka bir siteden gelen istek reddedildi")
            if is_admin_path(path):
                d = admin.check(self.client_address[0], self.headers)
                if not d.allowed:
                    extra = {"WWW-Authenticate": REALM} if d.status == 401 else {}
                    raise _Refused(d.status, d.message, extra)

        # -------------------------------------------------------------- routes

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            try:
                self._guard(url.path)
                if url.path in ("/", "/index.html"):
                    self._page("index.html")
                elif url.path in ("/admin", "/admin/"):
                    self._page("admin.html")
                elif url.path == "/healthz":
                    self._json({"ok": True})
                elif url.path == "/api/admin/analyses":
                    self._json(app.analyses())
                elif url.path == "/api/admin/dictionary":
                    self._json(app.dictionary_state())
                elif url.path == "/api/admin/words":
                    self._json(app.words_state())
                elif url.path.startswith("/api/admin/dictionary/table/"):
                    self._json(app.dictionary_table(unquote(url.path.rsplit("/", 1)[-1])))
                elif url.path.startswith("/api/admin/words/") and url.path.endswith("/export"):
                    self._xlsx_bytes(*app.words_export(url.path.split("/")[4]))
                elif url.path in ("/api/admin/dictionary/export", "/api/admin/dictionary/template"):
                    self._xlsx_bytes(*app.dictionary_export(url.path.endswith("template")))
                elif url.path.startswith("/api/admin/analysis/"):
                    self._json(app.analysis(url.path.rsplit("/", 1)[-1]))
                elif url.path == "/api/settings":
                    self._json(app.settings_get())
                elif url.path == "/api/llm":
                    self._json(app.llm_admin.state())
                elif url.path == "/api/llm/inventory":
                    self._json(app.llm_admin.inventory())
                elif url.path == "/api/status":
                    self._json(app.status())
                elif url.path == "/api/galaxy":
                    self._json(app.galaxy())
                elif url.path.startswith("/api/report/"):
                    self._xlsx(app.report(url.path.rsplit("/", 1)[-1]))
                elif url.path == "/api/list":
                    self._json(app.list_latest())
                elif url.path.startswith("/api/list/"):
                    parts = url.path.split("/")[3:]  # <id> [, "item", <n>] | [, "report"]
                    if len(parts) == 1:
                        self._json(app.list_job(parts[0]).snapshot())
                    elif parts[1:2] == ["report"]:
                        self._xlsx(app.list_report(parts[0]))
                    elif parts[1:2] == ["item"] and len(parts) == 3 and parts[2].isdigit():
                        voter = parse_qs(url.query).get("voter", [""])[0] or self.client_address[0]
                        self._json(app.list_item(parts[0], int(parts[2]), voter))
                    else:
                        self._error(404, "Bulunamadı")
                elif url.path == "/api/objects":
                    q = parse_qs(url.query).get("q", [""])[0]
                    self._json(app.objects(q))
                elif url.path.startswith("/api/object/"):
                    self._json(app.object_detail(unquote(url.path.split("/api/object/", 1)[1])))
                else:
                    self._error(404, "Bulunamadı")
            except _Refused as exc:
                self._error(exc.status, exc.message, exc.headers)
            except KeyError:
                self._error(404, "Kayıt bulunamadı")
            except FileNotFoundError as exc:  # e.g. the dictionary store before an import
                self._error(404, str(exc))
            except ValueError as exc:
                self._error(400, str(exc))
            except Exception:  # pragma: no cover - last-resort guard
                log.exception("GET %s", self.path)
                self._error(500, "Sunucu hatası (ayrıntı sunucu kaydında)")

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            started = time.perf_counter()
            try:
                # The body first (size-checked): answering before reading it would cut the
                # connection under a client still sending, and it would see an abort, not 401.
                raw = self._body()
                self._guard(url.path, post=True)
                if url.path == "/api/ask":
                    self._json(app.ask(_json_body(raw), self.client_address[0]))
                elif url.path == "/api/ask/cancel":
                    self._json(app.cancel_ask(_json_body(raw)))
                elif url.path == "/api/admin/analyses/clear":
                    self._json(app.clear_analyses(_json_body(raw)))
                elif url.path == "/api/admin/answers/clear":
                    self._json(app.clear_answers())
                elif url.path == "/api/admin/dictionary/import":
                    name = unquote(self.headers.get("X-Filename", "sozluk.xlsx"))
                    self._json(app.dictionary_import(raw, name))
                elif url.path in ("/api/admin/words/terms", "/api/admin/words/stopwords"):
                    self._json(app.words_save(url.path.rsplit("/", 1)[-1], _json_body(raw)))
                elif url.path.startswith("/api/admin/words/") and url.path.endswith("/import"):
                    self._json(app.words_import(url.path.split("/")[4], raw))
                elif url.path == "/api/list":
                    name = unquote(self.headers.get("X-Filename", "liste.xlsx"))
                    self._json(app.list_start(raw, name, self.client_address[0]))
                elif url.path.startswith("/api/list/") and url.path.endswith("/cancel"):
                    self._json(app.list_cancel(url.path.split("/")[3]))
                elif url.path.startswith("/api/list/") and url.path.endswith("/resume"):
                    self._json(app.list_resume(url.path.split("/")[3], self.client_address[0]))
                elif url.path == "/api/settings":
                    self._json(app.settings_save(_json_body(raw)))
                elif url.path == "/api/reindex":
                    self._json(app.reindex())
                elif url.path.startswith("/api/llm/") and url.path[9:] in LLM_POSTS:
                    action = getattr(app.llm_admin, LLM_POSTS[url.path[9:]])
                    self._json(action(_json_body(raw)))
                elif url.path == "/api/feedback":
                    self._json(app.feedback(_json_body(raw), self.client_address[0]))
                else:
                    self._error(404, "Bulunamadı")
            except _Refused as exc:
                self._error(exc.status, exc.message, exc.headers)
            except KeyError:
                self._error(404, "Kayıt bulunamadı")
            except FileNotFoundError as exc:
                self._error(404, str(exc))
            except json.JSONDecodeError:
                self._error(400, "Geçersiz JSON")
            except ValueError as exc:
                self._error(400, str(exc))
            except Exception:
                log.exception("POST %s", self.path)
                self._error(500, "Sunucu hatası (ayrıntı sunucu kaydında)")
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
    guard = AdminGuard.from_env()
    httpd = ThreadingHTTPServer((host, port), make_handler(app, guard))
    log.warning("VSA arayüzü: http://%s:%d", host, port)
    if not guard.protected:
        log.warning("Yönetim ekranı parolasız: yalnız bu makineden açılır (VSA_ADMIN_PASSWORD)")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
