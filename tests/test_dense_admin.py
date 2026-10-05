"""Vector index rebuild from the admin screen: background job, progress, stop, resume."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from vsa.config import load_settings
from vsa.pipeline import Engine
from vsa.web import dense_admin
from vsa.web.server import App


class FakeEmbedder:
    def __init__(self, gate: threading.Event | None = None) -> None:
        self.gate = gate  # embed blocks until set (to stop a build mid-way)
        self.calls = 0

    def ping(self) -> list[str]:
        return ["fake-emb"]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(10)
        return [[float(len(t)), 1.0, float(i), 0.5] for i, t in enumerate(texts)]


def make_app(dictionary: Path, tmp_path: Path, embedding: bool = True) -> App:
    llm = (
        "llm:\n  endpoint: http://127.0.0.1:9/v1\n  embedding_model: fake-emb\n"
        "dense:\n  enabled: true\n"
    )
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        f"dictionary:\n  path: {dictionary.as_posix()}\n"
        f"index:\n  dir: {(tmp_path / 'idx').as_posix()}\n"
        + (llm if embedding else ""),
        encoding="utf-8",
    )
    s = load_settings(settings_file)
    Engine.from_dictionary_file(s).save()
    return App(Engine.from_index(s), tmp_path / "out", tmp_path / "fb.jsonl", settings_file)


def wait_done(app: App) -> dict[str, object]:
    for _ in range(200):
        job = app.dense_admin.state()["job"]
        if job and job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("build did not finish")


def test_no_embedding_model_cannot_start(sample_dictionary_path: Path, tmp_path: Path) -> None:
    app = make_app(sample_dictionary_path, tmp_path, embedding=False)
    state = app.dense_admin.state()
    assert state["model"] == "" and state["need"] == "" and state["job"] is None
    with pytest.raises(ValueError, match="Embedding"):
        app.dense_admin.start()


def test_build_runs_in_background_and_reloads(
    sample_dictionary_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = make_app(sample_dictionary_path, tmp_path)
    monkeypatch.setattr(dense_admin, "embedding_client", lambda llm: FakeEmbedder())
    assert app.dense_admin.state()["need"] == "Vektör indeksi hiç kurulmadı"
    assert app.engine.dense is None
    started = app.dense_admin.start()
    assert started["job"]["status"] in ("running", "done")
    job = wait_done(app)
    assert job["status"] == "done" and job["done"] == job["total"] == 3 + job["objects"]
    state = app.dense_admin.state()
    assert state["need"] == "" and state["index_model"] == "fake-emb"
    assert app.engine.dense is not None  # engine reloaded with the new vectors


def test_stop_keeps_finished_batches_for_the_next_start(
    sample_dictionary_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = make_app(sample_dictionary_path, tmp_path)
    gate = threading.Event()
    fake = FakeEmbedder(gate)
    monkeypatch.setattr(dense_admin, "embedding_client", lambda llm: fake)
    app.dense_admin.start()
    with pytest.raises(ValueError, match="zaten"):
        app.dense_admin.start()
    with pytest.raises(ValueError, match="Vektör"):
        app.reindex()  # BM25 rebuild waits for the vector build
    while fake.calls == 0:
        time.sleep(0.01)
    app.dense_admin.cancel()
    gate.set()  # the running batch finishes; the next one is not started
    job = wait_done(app)
    assert job["status"] == "cancelled"
    keys = json.loads((tmp_path / "idx" / "dense_cache_keys.json").read_text(encoding="utf-8"))
    assert keys["model"] == "fake-emb" and len(keys["keys"]) == 3  # column batch kept

    fake.gate, fake.calls = None, 0
    app.dense_admin.start()
    assert wait_done(app)["status"] == "done"
    assert fake.calls == 1  # only the table profiles were left
