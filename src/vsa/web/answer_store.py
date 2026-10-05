"""Kept analyst answers on disk (ADR-035): ``data/cache/answers.jsonl``, one per line.

Read once at start, kept in memory, appended per new answer. A question's newer answer
replaces its older one (same words, same fingerprint); the file is compacted when it
holds replaced or surplus lines. Clearing deletes for good, like the analyses log.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_ENTRIES = 2000  # newest answers kept; ~30 KB each


@dataclass(slots=True)
class Hit:
    entry: dict[str, Any]
    match: str  # "aynı soru" | "aynı anlam"


class AnswerStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        lines = self.path.read_text(encoding="utf-8").splitlines()
        newest: dict[tuple[str, str], dict[str, Any]] = {}
        for line in lines:
            try:
                e = json.loads(line)
                newest[(e["text_key"], e["fingerprint"])] = e
            except (json.JSONDecodeError, KeyError, TypeError):
                continue  # a line cut short by a crash
        self._entries = sorted(newest.values(), key=lambda e: str(e["at"]))[-MAX_ENTRIES:]
        if len(self._entries) != len(lines):
            self._rewrite()

    def _rewrite(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self._entries),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("Cevap önbelleği yazılamadı: %s", exc)

    def lookup(
        self, text: str, meaning: str, fp: str, *, use_meaning: bool, max_age_days: int
    ) -> Hit | None:
        """The newest usable answer: the same words first, then the same meaning."""
        since = (datetime.now() - timedelta(days=max_age_days)).isoformat() if max_age_days else ""
        with self._lock:
            usable = [e for e in reversed(self._entries)
                      if e["fingerprint"] == fp and str(e["at"]) >= since]  # fmt: skip
        for e in usable:
            if e["text_key"] == text:
                return Hit(e, "aynı soru")
        if use_meaning and meaning:
            for e in usable:
                if e["meaning_key"] == meaning:
                    return Hit(e, "aynı anlam")
        return None

    def put(self, query: str, text: str, meaning: str, fp: str, result: dict[str, Any]) -> None:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "at": datetime.now().isoformat(timespec="seconds"),
            "query": query[:2000],
            "text_key": text,
            "meaning_key": meaning,
            "fingerprint": fp,
            "result": result,
        }
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries
                             if (e["text_key"], e["fingerprint"]) != (text, fp)]  # fmt: skip
            self._entries.append(entry)
            if len(self._entries) > MAX_ENTRIES or len(self._entries) <= before:
                self._entries = self._entries[-MAX_ENTRIES:]
                self._rewrite()
                return
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError as exc:  # the answer matters more than keeping it
                log.warning("Cevap önbelleğe yazılamadı: %s", exc)

    def forget(self, text: str, meaning: str) -> int:
        """Drop the answers of a question and of those meaning the same (a 👎 vote)."""
        with self._lock:
            kept = [
                e for e in self._entries
                if e["text_key"] != text and not (meaning and e["meaning_key"] == meaning)
            ]  # fmt: skip
            removed = len(self._entries) - len(kept)
            if removed:
                self._entries = kept
                self._rewrite()
        return removed

    def clear(self) -> int:
        with self._lock:
            removed = len(self._entries)
            self._entries = []
            self.path.unlink(missing_ok=True)
        return removed

    def stats(self, fp: str) -> dict[str, Any]:
        """How many answers are kept, and how many fit the current engine."""
        with self._lock:
            total = len(self._entries)
            usable = sum(1 for e in self._entries if e["fingerprint"] == fp)
            newest = self._entries[-1]["at"] if self._entries else ""
        return {"total": total, "usable": usable, "newest": newest, "path": str(self.path)}
