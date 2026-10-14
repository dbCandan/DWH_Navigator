"""The administration screen's view of analysis records (data-dictionary 008-analysis-records
Requirement 5-12, Decision 6-8, 13, 16).

Only terminal records are listed, summarized, shown and deleted. Periods and calendar days are
Istanbul time; ``until`` bounds a list, its summary and a deletion to what the manager saw. The
summary is computed as the source's screen computed it (``Analyses.kpi``, ``perf`` and
``quantile``), on the server and over every matching record.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import telemetry
from app.core.logging import log_event
from app.domain.analysis_records import Flow
from app.domain.turkish_text import fold
from app.infrastructure.repositories.analysis_record_repository import (
    AnalysisRecordRepository,
    RecordFilter,
    RecordRow,
)
from app.services.analysis.pipeline import ISTANBUL
from app.services.analysis.steps import PHASE_NAMES

logger = logging.getLogger("app.analysis")

PERIODS = ("today", "7d", "30d", "all")
DEFAULT_PERIOD = "7d"
WITH_TABLES = frozenset({"VAR", "KISMEN VAR"})


@dataclass(frozen=True, slots=True)
class Filters:
    """The administration screen's filters; ``period`` None means it was not given."""

    period: str | None = None
    flow: str | None = None
    asked_by: str | None = None
    q: str | None = None

    @property
    def any_given(self) -> bool:
        return any(value is not None for value in (self.period, self.flow, self.asked_by, self.q))


def quantile(ordered: Sequence[float], p: float) -> float:
    """The source's ``quantile``: linear interpolation between sorted values; 0 when empty."""

    if not ordered:
        return 0
    i = (len(ordered) - 1) * p
    lo, hi = int(i // 1), -int(-i // 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (i - lo)


def istanbul_midnight(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), ISTANBUL).astimezone(UTC)


def record_filter(filters: Filters, until: datetime) -> RecordFilter:
    period = filters.period or DEFAULT_PERIOD
    asked_from: datetime | None
    if period == "today":
        asked_from = istanbul_midnight(until.astimezone(ISTANBUL).date())
    elif period == "7d":
        asked_from = until - timedelta(days=7)
    elif period == "30d":
        asked_from = until - timedelta(days=30)
    else:
        asked_from = None
    return RecordFilter(
        until=until,
        asked_from=asked_from,
        flow=filters.flow,
        asker_public_id=filters.asked_by,
        folded_text=fold(filters.q) if filters.q else None,
    )


def row_fields(row: RecordRow) -> dict[str, Any]:
    """Requirement 6: a list row; no summary, answer or steps."""

    r = row.record
    return {
        "public_id": r.public_id,
        "asked_at": r.asked_at,
        "asked_by": {
            "public_id": row.asker_public_id,
            "display_name": row.asker_display_name,
            "kind": row.asker_kind,
        },
        "query": r.query,
        "origin": r.origin,
        "list_public_id": r.list_public_id,
        "list_file_name": r.list_file_name,
        "list_position": r.list_position,
        "flow": r.flow,
        "model": r.model,
        "verdict": r.verdict,
        "table_keys": list(r.table_keys or []),
        "unavailable_reason": r.unavailable_reason,
        "error": (
            {"code": r.error_code, "message": r.error_message or ""} if r.error_code else None
        ),
        "duration_ms": r.duration_ms,
    }


def phases_of(record: Any) -> dict[str, int]:
    return {name: int(getattr(record, f"phase_{name}_ms") or 0) for name in PHASE_NAMES}


def detail_fields(row: RecordRow) -> dict[str, Any]:
    """Requirement 10: the row, the summary, the reuse, the model use, the times, the phases
    and every step; never the full answer."""

    r = row.record
    return {
        **row_fields(row),
        "summary": r.summary,
        "reused": (
            {"at": r.reused_at, "query": r.reused_query or "", "match": r.reused_match}
            if r.reused_match
            else None
        ),
        "llm_calls": r.llm_calls,
        "prompt_tokens": r.prompt_tokens,
        "completion_tokens": r.completion_tokens,
        "dictionary_version": r.dictionary_version,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "queue_wait_ms": r.queue_wait_ms,
        "phases": phases_of(r),
        "steps_truncated": r.steps_truncated,
        "steps": list(r.steps or []),
    }


def summarize(figures: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Requirement 7 from the matching records' numbers."""

    answered = [f for f in figures if f["verdict"]]
    with_tables = [f for f in answered if f["verdict"] in WITH_TABLES]
    flows = {flow.value: 0 for flow in Flow}
    for f in figures:
        if f["flow"] in flows:
            flows[f["flow"]] += 1
    analyst = sorted(
        float(f["duration_ms"] or 0) for f in figures if f["flow"] == Flow.ANALYST.value
    )
    every = sorted(float(f["duration_ms"] or 0) for f in figures)
    phases = []
    for name in PHASE_NAMES:
        values = [int(f[f"phase_{name}_ms"] or 0) for f in figures]
        positive = [v for v in values if v > 0]
        phases.append(
            {
                "phase": name,
                "average_ms": sum(positive) / len(positive) if positive else None,
                "count": len(positive),
            }
        )
    askers: dict[str, dict[str, Any]] = {}
    for f in figures:
        entry = askers.setdefault(
            f["asker_public_id"],
            {
                "public_id": f["asker_public_id"],
                "display_name": f["asker_display_name"],
                "kind": f["asker_kind"],
                "count": 0,
            },
        )
        entry["count"] += 1
    return {
        "count": len(figures),
        "newest_at": max((f["asked_at"] for f in figures), default=None),
        "with_result": len(answered),
        "with_tables": len(with_tables),
        "flows": flows,
        "analyst_p50_ms": quantile(analyst, 0.5) if analyst else None,
        "analyst_p90_ms": quantile(analyst, 0.9) if analyst else None,
        "p50_ms": quantile(every, 0.5) if every else None,
        "p90_ms": quantile(every, 0.9) if every else None,
        "max_ms": every[-1] if every else None,
        "phases": phases,
        "llm_calls": sum(int(f["llm_calls"] or 0) for f in figures),
        "prompt_tokens": sum(int(f["prompt_tokens"] or 0) for f in figures),
        "completion_tokens": sum(int(f["completion_tokens"] or 0) for f in figures),
        "askers": sorted(askers.values(), key=lambda a: (-a["count"], a["display_name"])),
    }


class AnalysisRecordsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.records = AnalysisRecordRepository(session)

    async def page(
        self, tenant_id: int, filters: Filters, until: datetime, page: int, page_size: int
    ) -> dict[str, Any]:
        rows, total = await self.records.page(
            tenant_id,
            record_filter(filters, until),
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return {
            "items": [row_fields(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "snapshot_at": until,
        }

    async def summary(self, tenant_id: int, filters: Filters, until: datetime) -> dict[str, Any]:
        figures = await self.records.figures(tenant_id, record_filter(filters, until))
        return {**summarize(figures), "snapshot_at": until}

    async def daily_counts(self, tenant_id: int, days: int, now: datetime) -> dict[str, Any]:
        """Requirement 8: Istanbul calendar days, oldest first, zero for a day without one."""

        today = now.astimezone(ISTANBUL).date()
        first = today - timedelta(days=days - 1)
        counts = {first + timedelta(days=i): [0, 0] for i in range(days)}
        for asked_at, verdict in await self.records.verdicts_since(
            tenant_id, istanbul_midnight(first)
        ):
            day = asked_at.astimezone(ISTANBUL).date()
            if day in counts:
                counts[day][0 if verdict in WITH_TABLES else 1] += 1
        return {
            "days": [
                {"date": day.isoformat(), "with_tables": c[0], "without_tables": c[1]}
                for day, c in counts.items()
            ]
        }

    async def askers(self, tenant_id: int) -> dict[str, Any]:
        return {
            "items": [
                {"public_id": public_id, "display_name": name, "kind": kind}
                for public_id, name, kind in await self.records.askers(tenant_id)
            ]
        }

    async def detail(self, tenant_id: int, public_id: str) -> dict[str, Any] | None:
        row = await self.records.terminal(tenant_id, public_id)
        return detail_fields(row) if row is not None else None

    async def delete(
        self,
        tenant_id: int,
        filters: Filters,
        until: datetime,
        *,
        everything: bool,
        actor_public_id: str,
    ) -> dict[str, int]:
        """Requirement 11: physically, in one transaction; the saved answers' links empty."""

        chosen = Filters(period="all") if everything else filters
        deleted = await self.records.delete_matching(tenant_id, record_filter(chosen, until))
        remaining = await self.records.count_terminal(tenant_id)
        await self.session.commit()
        telemetry.record_analysis_records_deleted(deleted)
        log_event(
            logger,
            "analysis_record.deleted",
            count=deleted,
            scope="all" if everything else "filter",
            user_public_id=actor_public_id,
        )
        return {"deleted_count": deleted, "remaining_count": remaining}
