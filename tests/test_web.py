"""M6: web API end to end on the sample dictionary (real HTTP, random port)."""

from __future__ import annotations

import json
import threading
import urllib.error
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
def base_url(sample_dictionary_path: Path, tmp_path: Path) -> Iterator[str]:
    s = Settings()
    s.dictionary.path = str(sample_dictionary_path)
    engine = Engine.from_dictionary_file(s)
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


def test_batch_json(base_url: str) -> None:
    fields = [
        {
            "tr": "Limit Doluluk",
            "en": "CardLimitFullness",
            "description": "Kart limit doluluk oranı",
        }
    ]
    status, data = post(base_url + "/api/batch", {"name": "t", "fields": fields})
    assert status == 200 and data["fields"][0]["status"]


def test_explorer(base_url: str) -> None:
    _, body, _ = get(base_url + "/api/objects?q=limit")
    rows = json.loads(body)
    assert {r["name"] for r in rows} >= {"vCardLimitFullness", "vCreditCardLimit"}
    _, body, _ = get(base_url + "/api/object/" + rows[0]["key"])
    assert json.loads(body)["columns"]
    status, _, _ = get(base_url + "/api/object/DB.S.yok")
    assert status == 404


def test_feedback(base_url: str, tmp_path: Path) -> None:
    status, data = post(base_url + "/api/feedback", {"query": "q", "object": "o", "vote": "up"})
    assert status == 200 and data["ok"]
    lines = (tmp_path / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["vote"] == "up"
    status, _ = post(base_url + "/api/feedback", {"vote": "maybe"})
    assert status == 400


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
