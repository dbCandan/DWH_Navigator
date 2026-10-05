"""Feedback loop, first step (HANDOVER §17 M7). Does file I/O.

Thumbs from the web UI land in ``data/feedback.jsonl``. This module turns them into
*candidate* golden-set items for review — they are not added to the golden set
automatically, because only verified requests belong there (§13.3).

The same votes shape the answer shown when a question comes again (ADR-036): see
``assess`` and ``apply`` below (pure functions; the server reads the file).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from vsa.scoring.combine import level_for


@dataclass(slots=True)
class QueryFeedback:
    query: str
    up: list[str] = field(default_factory=list)
    down: list[str] = field(default_factory=list)


def load_feedback(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[QueryFeedback]:
    """Latest vote per (query, object) wins. Votes of the removed target-table mode
    (with a ``field``) are ignored (ADR-033)."""
    latest: dict[tuple[str, str], str] = {}
    for r in rows:
        if not r.get("field") and r.get("scope", "object") == "object":
            latest[(r.get("query", ""), r.get("object", ""))] = r.get("vote", "")
    by_query: dict[str, QueryFeedback] = {}
    for (query, obj), vote in latest.items():
        fb = by_query.setdefault(query, QueryFeedback(query))
        if vote == "up":
            fb.up.append(obj)
        elif vote == "down":
            fb.down.append(obj)
    return list(by_query.values())


def golden_candidates(summary: list[QueryFeedback]) -> list[dict[str, Any]]:
    today = date.today().isoformat()
    items: list[dict[str, Any]] = []
    for i, fb in enumerate((s for s in summary if s.up), 1):
        item: dict[str, Any] = {
            "id": f"fb-{today}-{i:02d}",
            "query": fb.query,
            "mode": "ask",
            "expected_objects": sorted(fb.up),
            "source": f"geri-bildirim-{today}",
            "notes": "Arayüz geri bildiriminden aday; doğrulanınca golden_set.yaml'a taşıyın.",
        }
        if fb.down:
            item["rejected_objects"] = sorted(fb.down)
        items.append(item)
    return items


def export_candidates(feedback_path: Path, out_path: Path) -> int:
    items = golden_candidates(summarize(load_feedback(feedback_path)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "# Golden set ADAYLARI — gözden geçirip doğrulananları tests/golden_set.yaml'a ekleyin.\n"
        + yaml.safe_dump(items, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    return len(items)


# --------------------------------------------------------------------------- reading votes
# How earlier thumbs shape the answer shown for a question (ADR-036).

SAME_WORDS = 1.0  # a vote on the very same question (text key, ADR-035)
SAME_MEANING = 0.6  # a vote on a question meaning the same (meaning key)
OTHER_DICTIONARY = 0.5  # cast on another dictionary version: the table may have changed
HALF_LIFE_DAYS = 180.0
PRIOR = 2.0  # one imaginary 👍 and one 👎: a single vote does not decide alone
REJECT_WEIGHT = 1.5  # about two people
REJECT_SUPPORT = -0.3
APPROVE_SUPPORT = 0.2
SCORE_NUDGE = 0.15  # shown confidence × (1 + nudge × support)
ANSWER_REJECT_SHARE = 0.6


@dataclass(slots=True)
class Tally:
    """Weighted votes of distinct people on one table (or on the whole answer)."""

    up: float = 0.0
    down: float = 0.0
    people_up: int = 0
    people_down: int = 0
    reasons: list[str] = field(default_factory=list)  # the 👎 notes, newest first

    @property
    def support(self) -> float:
        """-1..1, shrunk towards 0 while there are few votes."""
        return (self.up - self.down) / (self.up + self.down + PRIOR)

    @property
    def status(self) -> str:
        if self.down >= REJECT_WEIGHT and self.support <= REJECT_SUPPORT:
            return "rejected"
        if self.up > 0 and self.support >= APPROVE_SUPPORT:
            return "approved"
        if self.up > 0 and self.down > 0:
            return "disputed"
        if self.down > 0:
            return "doubted"
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "up": self.people_up,
            "down": self.people_down,
            "support": round(self.support, 3),
            "status": self.status,
            "reasons": self.reasons[:3],
        }


@dataclass(slots=True)
class FeedbackView:
    """What earlier votes say about one question."""

    objects: dict[str, Tally] = field(default_factory=dict)
    answer: Tally = field(default_factory=Tally)
    mine: dict[str, str] = field(default_factory=dict)  # this voter's votes; "" = the answer

    @property
    def answer_rejected(self) -> bool:
        """Enough people found the whole answer useless: ask the analyst again."""
        a = self.answer
        return a.down >= REJECT_WEIGHT and a.down / (a.up + a.down) >= ANSWER_REJECT_SHARE


def _age_weight(at: str, now: datetime) -> float:
    try:
        days = max(0.0, (now - datetime.fromisoformat(at)).total_seconds() / 86400)
    except (TypeError, ValueError):
        return 1.0
    return float(0.5 ** (days / HALF_LIFE_DAYS))


def assess(
    rows: list[dict[str, Any]],
    text_key: str,
    meaning_key: str = "",
    *,
    dictionary_version: str = "",
    voter: str = "",
    answer_since: str = "",
    now: datetime | None = None,
) -> FeedbackView:
    """Tally the votes cast on this question or on one meaning the same. Each person's
    latest vote per table counts once (they may change their mind); old votes, votes on
    a merely similar question and votes on another dictionary version weigh less.

    Votes on the whole answer judge one answer, not the question: only those cast since
    ``answer_since`` (when that answer was written) count, so a fresh analysis starts
    clean instead of inheriting the 👎 that retired its predecessor."""
    now = now or datetime.now()
    since = answer_since.replace(" ", "T")
    latest: dict[tuple[str, str], tuple[dict[str, Any], float]] = {}
    for r in rows:
        if r.get("field"):
            continue  # removed target-table mode (ADR-033)
        if r.get("scope") == "answer" and since and str(r.get("at", "")) < since:
            continue
        if text_key and r.get("text_key") == text_key:
            match = SAME_WORDS
        elif meaning_key and r.get("meaning_key") == meaning_key:
            match = SAME_MEANING
        else:
            continue
        obj = str(r.get("object", "")) if r.get("scope", "object") == "object" else ""
        latest[(str(r.get("voter", "")), obj)] = (r, match)
    view = FeedbackView()
    for (who, obj), (r, match) in sorted(latest.items(), key=lambda kv: str(kv[1][0].get("at"))):
        w = match * _age_weight(str(r.get("at", "")), now)
        voted_on = r.get("dictionary_version", dictionary_version)
        if dictionary_version and voted_on != dictionary_version:
            w *= OTHER_DICTIONARY
        tally = view.objects.setdefault(obj, Tally()) if obj else view.answer
        if r.get("vote") == "up":
            tally.up += w
            tally.people_up += 1
        elif r.get("vote") == "down":
            tally.down += w
            tally.people_down += 1
            note = str(r.get("note", "")).strip()
            if note:
                tally.reasons.insert(0, note)
        if voter and who == voter and match == SAME_WORDS:
            view.mine[obj] = str(r.get("vote", ""))
    return view


def apply(
    data: dict[str, Any], view: FeedbackView, known: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """The answer as earlier votes would have it, in its serialized form (the analysis
    and its Excel report stay as written):

    * every table carries its tally; its confidence is nudged by the support (±15 %);
    * a table people rejected leaves the suggestions for ``rejected`` — shown apart,
      with the reasons given, not hidden;
    * a near candidate people approved for this question joins the suggestions, marked
      ``promoted``; an approved table the answer does not hold at all is listed under
      ``endorsed``, only while the dictionary still has it (``known``, ADR-002);
    * the suggestions are re-ranked on the nudged confidence.
    """
    out = dict(data)

    def tagged(m: dict[str, Any]) -> dict[str, Any]:
        t = view.objects.get(m["key"])
        m = {**m, "votes": t.to_dict() if t else None}
        if t and (t.up or t.down):
            m["score_before"] = m["score"]
            nudged = m["score"] * (1 + SCORE_NUDGE * t.support)
            m["score"] = round(min(1.0, max(0.0, nudged)), 4)
            m["level"] = level_for(m["score"]).value
        return m

    def status(m: dict[str, Any]) -> str:
        t = view.objects.get(m["key"])
        return t.status if t else ""

    shown: list[dict[str, Any]] = []
    near: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for m in out.get("objects", []):
        (rejected if status(m) == "rejected" else shown).append(tagged(m))
    for m in out.get("near", []):
        if status(m) == "approved":
            shown.append({**tagged(m), "promoted": True})
        else:
            (rejected if status(m) == "rejected" else near).append(tagged(m))
    shown.sort(key=lambda m: -float(m["score"]))
    for i, m in enumerate(shown, 1):
        m["rank"] = i
    present = {m["key"] for m in [*shown, *near, *rejected]}
    endorsed = [
        {**known[key], "key": key, "votes": t.to_dict()}
        for key, t in sorted(view.objects.items(), key=lambda kv: -kv[1].support)
        if t.status == "approved" and key not in present and key in known
    ]
    out.update(objects=shown, near=near, rejected=rejected, endorsed=endorsed)
    out["feedback"] = {
        "answer": view.answer.to_dict(),
        "answer_rejected": view.answer_rejected,
        "mine": view.mine,
    }
    return out
