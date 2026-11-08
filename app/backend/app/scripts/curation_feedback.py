"""The admin's corrections as gold-set rows: what the model got wrong and the text it should give.

Every field an admin wrote in an approved update (report lines ``*_admin_edited``) becomes one
JSON line: the record, the field, the model's text and the admin's. The lines join the gold set
the local models are measured on, so a mistake the admin fixed once is a test from then on.

usage (backend container): python -m app.scripts.curation_feedback --output feedback.jsonl [--since 2026-11-01]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

import app.db.base  # noqa: F401  # populate mapper metadata
from app.db.session import async_session_factory
from app.domain.models.dictionary_sync import DictionarySyncChange, DictionarySyncRun

EDIT_KINDS = ("table_admin_edited", "column_admin_edited")


def feedback_row(run: Any, change: Any) -> dict[str, Any]:
    return {
        "t": "col" if change.column_name else "obj",
        "obj": change.table_key,
        "col": change.column_name,
        "field": change.field,
        "model_text": change.old_value,
        "gold_text": change.new_value,
        "run": run.public_id,
        "approved_at": run.finished_at.isoformat() if run.finished_at else "",
        "source": "yonetici",
    }


async def collect(since: datetime | None) -> list[dict[str, Any]]:
    query = (
        select(DictionarySyncRun, DictionarySyncChange)
        .join(
            DictionarySyncChange,
            DictionarySyncChange.dictionary_sync_run_id == DictionarySyncRun.dictionary_sync_run_id,
        )
        .where(DictionarySyncRun.status == "completed", DictionarySyncChange.kind.in_(EDIT_KINDS))
        .order_by(DictionarySyncRun.finished_at, DictionarySyncChange.position)
    )
    if since is not None:
        query = query.where(DictionarySyncRun.finished_at >= since)
    async with async_session_factory() as session:
        rows = (await session.execute(query)).all()
    # A field fixed several times: the model's own text from the first fix, the admin's last word.
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for run, change in rows:
        item = feedback_row(run, change)
        key = (item["obj"].casefold(), item["col"].casefold(), item["field"])
        if key in latest:
            item["model_text"] = latest[key]["model_text"]
        latest[key] = item
    return list(latest.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--since", type=lambda v: datetime.fromisoformat(v).replace(tzinfo=UTC))
    args = parser.parse_args()
    items = asyncio.run(collect(args.since))
    with args.output.open("w", encoding="utf-8") as out:
        for item in items:
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"{len(items)} düzeltme yazıldı: {args.output}")


if __name__ == "__main__":
    main()
