"""M6: web API end to end on the sample dictionary (real HTTP, random port)."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from vsa.config import Settings
from vsa.pipeline import Engine
from vsa.web.server import App, make_handler


@pytest.fixture
def base_url(
    sample_dictionary_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    engine = Engine.from_dictionary_file(s)
    # No model in tests: the rule engine's ranking stands in for an answer, so the page,
    # report and log plumbing can be exercised (users never see it, ADR-038).
    monkeypatch.setattr(Engine, "analyze", Engine.rule_answer)
    app = App(engine, tmp_path / "out", tmp_path / "feedback.jsonl")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(url: str) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def post(url: str, body: Any) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_index_page_is_self_contained(base_url: str) -> None:
    status, body, ctype = get(base_url + "/")
    html = body.decode("utf-8")
    assert status == 200 and ctype.startswith("text/html")
    # Closed network: no external scripts, styles or fonts.
    assert "http://" not in html.replace("http://www.w3.org", "")
    assert "https://" not in html


def test_status(base_url: str) -> None:
    status, body, _ = get(base_url + "/api/status")
    data = json.loads(body)
    assert status == 200 and data["columns"] == 3 and data["llm"] == ""
    assert data["llm_state"]["state"] == "none"  # ADR-034: the page warns
    assert len(data["updated"]) == 10  # ISO date of the dictionary file


def test_ask_and_report(base_url: str) -> None:
    status, data = post(base_url + "/api/ask", {"query": "kart limit doluluk oranı"})
    assert status == 200
    assert data["objects"][0]["name"] == "vCardLimitFullness"
    assert data["objects"][0]["columns"][0]["column"]
    status, body, ctype = get(f"{base_url}/api/report/{data['report_id']}")
    assert status == 200 and "spreadsheetml" in ctype and body[:2] == b"PK"


def test_ask_validation(base_url: str) -> None:
    status, data = post(base_url + "/api/ask", {"query": "  "})
    assert status == 400 and "boş" in data["error"]


def _xlsx(cells: list[str]) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for v in cells:
        ws.append([v])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_term_list_end_to_end(base_url: str) -> None:
    """Upload a one-column list, follow its progress, read a term, get one report."""
    body = _xlsx(["Terim", "kart limit doluluk oranı", "", "uzay gemisi yakıtı",
                  "Kart limit doluluk oranı"])  # fmt: skip
    req = urllib.request.Request(base_url + "/api/list", data=body,
                                 headers={"X-Filename": "terimler.xlsx"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=30) as r:
        job = json.loads(r.read())
    assert [i["term"] for i in job["items"]] == ["kart limit doluluk oranı", "uzay gemisi yakıtı"]
    for _ in range(300):
        _, raw, _ = get(f"{base_url}/api/list/{job['id']}")
        job = json.loads(raw)
        if not job["running"]:
            break
        time.sleep(0.05)
    assert job["done"] == 2 and [i["state"] for i in job["items"]] == ["bitti", "bitti"]
    assert job["header"] == "Terim" and len(job["notes"]) == 2  # a blank row and a repeat
    assert job["items"][1]["verdict"] == "BULUNAMADI"
    assert json.loads(get(base_url + "/api/list")[1])["id"] == job["id"]
    status, raw, _ = get(f"{base_url}/api/list/{job['id']}/item/1")
    item = json.loads(raw)
    assert status == 200 and item["query"] == "kart limit doluluk oranı" and item["report_id"]
    status, raw, ctype = get(f"{base_url}/api/list/{job['id']}/report")
    assert status == 200 and "spreadsheet" in ctype and raw[:2] == b"PK"
    assert get(f"{base_url}/api/list/yok")[0] == 404


def test_term_list_resumes_after_stop(
    sample_dictionary_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Durdur, then Devam et: answered terms are kept, the rest are asked, none twice."""
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    engine = Engine.from_dictionary_file(s)
    gate, asked = threading.Event(), []

    def analyze(self: Engine, query: str, top_n: int = 5) -> Any:
        asked.append(query)
        gate.wait(10)  # the first term is still running when the list is stopped
        return Engine.rule_answer(self, query, top_n)

    monkeypatch.setattr(Engine, "analyze", analyze)
    app = App(engine, tmp_path / "out", tmp_path / "feedback.jsonl")

    def finish(jid: str) -> dict[str, Any]:
        for _ in range(400):
            snap = app.list_job(jid).snapshot()
            if not snap["running"]:
                return snap
            time.sleep(0.05)
        raise AssertionError("liste bitmedi")

    job = app.list_start(_xlsx(["Terim", "kart limit", "müşteri yaşı", "uzay yakıtı"]), "t.xlsx")
    for _ in range(100):
        if asked:
            break
        time.sleep(0.02)
    app.list_cancel(job["id"])
    gate.set()
    snap = finish(job["id"])
    assert snap["cancelled"] and snap["done"] == 1
    assert [i["state"] for i in snap["items"]] == ["bitti", "durduruldu", "durduruldu"]

    snap = app.list_resume(job["id"])
    assert snap["running"] and not snap["cancelled"]
    snap = finish(job["id"])
    assert snap["done"] == 3 and not snap["cancelled"]
    assert asked == ["kart limit", "müşteri yaşı", "uzay yakıtı"]  # the first was not asked again
    with pytest.raises(ValueError, match="devam edecek terim yok"):
        app.list_resume(job["id"])


def test_term_list_rejects_bad_files(base_url: str) -> None:
    def upload(body: bytes) -> tuple[int, dict[str, Any]]:
        req = urllib.request.Request(base_url + "/api/list", data=body)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    status, data = upload(b"not an excel file")
    assert status == 400 and "Excel (.xlsx) olarak okunamadı" in data["error"]
    status, data = upload(_xlsx(["Terim"]))
    assert status == 400 and "aranacak terim yok" in data["error"]


def test_target_table_endpoint_is_gone(base_url: str) -> None:
    assert post(base_url + "/api/batch", {"fields": []})[0] == 404


def test_explorer(base_url: str) -> None:
    _, body, _ = get(base_url + "/api/objects?q=limit")
    rows = json.loads(body)["items"]
    assert {r["name"] for r in rows} >= {"vCardLimitFullness", "vCreditCardLimit"}
    assert {r["match"] for r in rows} == {"ad"}  # both names contain "limit"
    _, body, _ = get(base_url + "/api/object/" + rows[0]["key"])
    detail = json.loads(body)
    assert detail["columns"] and isinstance(detail["groups"], list)
    status, _, _ = get(base_url + "/api/object/DB.S.yok")
    assert status == 404


def test_feedback(base_url: str, tmp_path: Path) -> None:
    status, data = post(base_url + "/api/feedback", {"query": "q", "object": "o", "vote": "up"})
    assert status == 200 and data["ok"]
    lines = (tmp_path / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    assert row["vote"] == "up" and row["text_key"] == "q" and row["voter"]
    assert data["votes"]["up"] == 1
    status, _ = post(base_url + "/api/feedback", {"vote": "maybe"})
    assert status == 400


def test_answer_votes_drop_the_kept_answer(base_url: str) -> None:
    for who in ("a", "b"):
        body = {"query": "yeni soru", "scope": "answer", "vote": "down", "voter": who}
        status, data = post(base_url + "/api/feedback", body)
        assert status == 200
    assert data["answer_rejected"] is True


def test_ask_carries_earlier_votes(base_url: str) -> None:
    q = "kredi kartı limit doluluk oranı"
    _, first = post(base_url + "/api/ask", {"query": q, "top": 5})
    best = first["objects"][0]["key"]
    for who in ("a", "b"):
        post(base_url + "/api/feedback", {"query": q, "object": best, "vote": "down", "voter": who})
    _, again = post(base_url + "/api/ask", {"query": q, "top": 5, "voter": "a"})
    assert best not in [m["key"] for m in again["objects"]]
    assert again["rejected"][0]["key"] == best
    assert again["feedback"]["mine"] == {best: "down"}


def test_feedback_to_golden_candidates(tmp_path: Path) -> None:
    from vsa.feedback import export_candidates

    fb = tmp_path / "fb.jsonl"
    rows = [
        {"query": "q1", "object": "DB.S.vA", "field": "", "vote": "down"},
        {"query": "q1", "object": "DB.S.vA", "field": "", "vote": "up"},  # latest wins
        {"query": "q1", "object": "DB.S.vB", "field": "", "vote": "down"},
        {"query": "q2", "object": "DB.S.vC", "field": "", "vote": "down"},
    ]
    fb.write_text("\n".join(json.dumps(r) for r in rows) + "\nbroken\n", encoding="utf-8")
    out = tmp_path / "cand.yaml"
    assert export_candidates(fb, out) == 1
    import yaml

    items = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert items[0]["expected_objects"] == ["DB.S.vA"]
    assert items[0]["rejected_objects"] == ["DB.S.vB"]


def test_explorer_content_and_column_layers(base_url: str) -> None:
    # "doluluk oranı" is in no table or column name — only the content layer finds it.
    _, body, _ = get(base_url + "/api/objects?q=" + urllib.parse.quote("doluluk oranı"))
    data = json.loads(body)
    first = data["items"][0]
    assert first["name"] == "vCardLimitFullness" and first["match"] == "içerik"
    assert first["score"] > 0 and "CardLimitFullnessToday" in first["matched"]
    assert any("doluluk oranı" in c for c in data["concepts"])
    # A column-name fragment that is not in any table name.
    _, body, _ = get(base_url + "/api/objects?q=PartyId")
    items = json.loads(body)["items"]
    assert items and items[0]["match"] in ("içerik", "kolon adı")
    assert any("CustomerPartyId" in i.get("matched", []) for i in items)


def test_explorer_short_and_empty_queries(base_url: str) -> None:
    _, body, _ = get(base_url + "/api/objects?q=")
    assert len(json.loads(body)["items"]) == 2  # browse mode lists every object
    _, body, _ = get(base_url + "/api/objects?q=vc")
    assert {i["match"] for i in json.loads(body)["items"]} == {"ad"}  # < 3 chars: names only


def test_galaxy(base_url: str) -> None:
    _, body, _ = get(base_url + "/api/galaxy")
    stars = json.loads(body)
    assert {s["name"] for s in stars} == {"vCardLimitFullness", "vCreditCardLimit"}
    assert all(s["group"] and s["columns"] > 0 for s in stars)


def test_explorer_not_blocked_by_a_running_question(
    sample_dictionary_path: Path, tmp_path: Path
) -> None:
    """The explorer must answer while an analyst question holds the engine lock."""
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    app = App(Engine.from_dictionary_file(s), tmp_path / "out", tmp_path / "fb.jsonl")
    with app.lock:  # a long question in progress
        result = app.objects("doluluk oranı")
    assert result["items"] and result["items"][0]["match"] == "içerik"


@pytest.fixture
def app_with_settings(sample_dictionary_path: Path, tmp_path: Path) -> App:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        f"dictionary:\n  path: {sample_dictionary_path.as_posix()}\n"
        f"index:\n  dir: {(tmp_path / 'idx').as_posix()}\n",
        encoding="utf-8",
    )
    from vsa.config import load_settings

    s = load_settings(settings_file)
    Engine.from_dictionary_file(s).save()
    return App(Engine.from_index(s), tmp_path / "out", tmp_path / "fb.jsonl", settings_file)


def test_settings_roundtrip(app_with_settings: App) -> None:
    app = app_with_settings
    got = app.settings_get()
    assert [p["id"] for p in got["pages"]] == ["llm", "search", "data"]
    pages = {p["id"] for p in got["pages"]}
    assert all(s["page"] in pages for s in got["sections"])
    res = app.settings_save({"values": {"expansion.weight": 0.4}})
    assert res["ok"] and res["changed"] == ["Eş anlamlı terimlerin ağırlığı"]
    assert app.engine.settings.expansion.weight == 0.4  # engine reloaded
    assert "weight: 0.4" in app.settings_path.read_text(encoding="utf-8")


def test_model_connection_is_not_on_the_screen(app_with_settings: App) -> None:
    """The plain settings pages never carry the model connection (that is the LLM page,
    ADR-032), and saving them keeps the llm section of the file. The analyst's reading
    settings are on the "Arama ve cevap" page (ADR-040)."""
    app = app_with_settings
    path = app.settings_path
    path.write_text(
        path.read_text(encoding="utf-8")
        + "llm:\n  enabled: false\n  endpoint: http://spark-1:8000/v1\n  model: m\n"
        "  api_key: gizli\nanalyst:\n  family_tables: 3\n",
        encoding="utf-8",
    )
    got = app.settings_get()
    keys = {f["key"] for sec in got["sections"] for f in sec["fields"]}
    assert not {k for k in keys if k.startswith(("llm.", "cloud."))}
    assert "analyst.detail_columns" in keys
    assert "gizli" not in json.dumps(got) and "spark-1" not in json.dumps(got)
    with pytest.raises(ValueError, match="Bilinmeyen"):
        app.settings_save({"values": {"llm.endpoint": "http://evil/v1"}})
    app.settings_save({"values": {"search.top_k_objects": 7}})
    s = app.engine.settings
    assert s.search.top_k_objects == 7 and s.analyst.family_tables == 3  # not on the screen
    assert (s.llm.endpoint, s.llm.model, s.llm.api_key) == ("http://spark-1:8000/v1", "m", "gizli")


def test_settings_validation(app_with_settings: App) -> None:
    with pytest.raises(ValueError, match="arasında"):
        app_with_settings.settings_save({"values": {"expansion.weight": 3}})
    with pytest.raises(ValueError, match="Bilinmeyen"):
        app_with_settings.settings_save({"values": {"search.hack": 1}})


def test_settings_reindex_flag_and_rebuild(app_with_settings: App) -> None:
    app = app_with_settings
    res = app.settings_save({"values": {"search.field_weights.name": 4.0}})
    assert res["reindex_needed"] == ["Kolon adı ağırlığı"]
    out = app.reindex()
    assert out["ok"] and out["columns"] == 3 and app.reindex_pending == []


def test_admin_page_served_and_not_linked(base_url: str) -> None:
    status, body, ctype = get(base_url + "/admin")
    html = body.decode("utf-8")
    assert status == 200 and "Kaydet ve uygula" in html and "Analizler" in html
    assert "https://" not in html
    # Reached only by typing the address: the app does not link it, the old one is gone.
    assert "/admin" not in get(base_url + "/")[1].decode("utf-8")
    assert get(base_url + "/ayarlar")[0] == 404


def test_ask_is_logged_for_admin(base_url: str, tmp_path: Path) -> None:
    status, data = post(base_url + "/api/ask", {"query": "kart limit doluluk oranı"})
    assert status == 200
    lines = (tmp_path / "logs" / "analyses.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    assert entry["query"] == "kart limit doluluk oranı" and entry["ip"] == "127.0.0.1"
    assert entry["flow"] == "yapılamadı" and entry["verdict"] and entry["ms"] >= 0
    names = [s["name"] for s in entry["spans"]]
    assert {"Sırada bekleme", "BM25 arama", "Kolon skorlama"} <= set(names)

    status, body, _ = get(base_url + "/api/admin/analyses")
    listed = json.loads(body)["items"][0]
    assert "spans" not in listed and "BM25 arama" in listed["steps"]
    status, body, _ = get(f"{base_url}/api/admin/analysis/{listed['id']}")
    assert status == 200 and json.loads(body)["spans"]
    assert get(base_url + "/api/admin/analysis/nope")[0] == 404


def test_lab_and_cloud_endpoints_are_gone(base_url: str) -> None:
    assert get(base_url + "/api/lab")[0] == 404
    assert get(base_url + "/api/cloud-models")[0] == 404
    assert post(base_url + "/api/settings/test", {})[0] == 404
    html = get(base_url + "/admin")[1].decode("utf-8")
    assert "laboratuvar" not in html and "/api/lab" not in html


def test_stopped_ask_is_cancelled_and_logged(
    base_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The button's call: the question ends at once, as "durduruldu", without a rule answer."""
    from vsa import cancel

    started = threading.Event()

    def slow_analyze(self: Engine, query: str, top_n: int = 5) -> Any:
        started.set()
        cancel.sleep(30)  # stands in for a long LLM call
        raise AssertionError("not stopped")

    monkeypatch.setattr(Engine, "analyze", slow_analyze)
    result: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: result.update(
        post(base_url + "/api/ask", {"query": "uzun soru", "ask_id": "abc123"})[1]))
    worker.start()
    assert started.wait(5)
    assert post(base_url + "/api/ask/cancel", {"ask_id": "abc123"}) == (200, {"ok": True})
    worker.join(5)
    assert not worker.is_alive()
    assert result == {"cancelled": True, "ask_id": "abc123"}
    assert post(base_url + "/api/ask/cancel", {"ask_id": "abc123"})[1] == {"ok": False}
    lines = (tmp_path / "logs" / "analyses.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    assert entry["flow"] == "durduruldu" and entry["error"] == "Kullanıcı durdurdu"
    assert any(s["name"] == "Durduruldu" for s in entry["spans"])


def test_clear_analyses(app_with_settings: App) -> None:
    """Delete chosen records or all of them; never by omission; no backup is left."""
    app = app_with_settings
    app.analyses_path.parent.mkdir(parents=True, exist_ok=True)
    app.analyses_path.write_text(
        "".join(json.dumps({"id": i, "query": i}) + "\n" for i in ("a", "b", "c")), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="seçilmedi"):
        app.clear_analyses({})
    assert app.clear_analyses({"ids": ["a", "c"]}) == {"removed": 2, "kept": 1}
    assert [e["id"] for e in app.analyses()["items"]] == ["b"]
    assert not app.analyses_path.with_name(app.analyses_path.name + ".bak").exists()
    assert app.clear_analyses({"all": True}) == {"removed": 1, "kept": 0}
    assert app.analyses()["items"] == []


def test_settings_change_does_not_wait_for_a_running_question(app_with_settings: App) -> None:
    """A question holds the engine lock for minutes with the analyst; saving settings
    builds the new engine beside it instead of waiting (the old one finishes the question)."""
    app = app_with_settings
    old = app.engine
    app.lock.acquire()  # a question is being answered
    try:
        done = threading.Event()
        worker = threading.Thread(
            target=lambda: (app.settings_save({"values": {"expansion.weight": 0.4}}),
                            done.set()))  # fmt: skip
        worker.start()
        assert done.wait(20), "saving waited for the running question"
    finally:
        app.lock.release()
    assert app.engine is not old and app.engine.settings.expansion.weight == 0.4
    assert app.engine.features is old.features  # same dictionary: column texts not redone
