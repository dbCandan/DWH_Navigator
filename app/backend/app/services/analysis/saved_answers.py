"""Saved answers (data-dictionary 004-question-analysis Requirement 13-15, Decision 3, 8, 9, 24).

The source's ADR-035 rules over PostgreSQL: the same question first, then (when allowed) a question
meaning the same, only under the same fingerprint and within ``cache.max_age_days``; the answer is
rebuilt with the current dictionary and is not used when one of its columns is gone. Only the
analyst's answers are written; the newest 2000 stay. A store failure never stops an analysis:
lookups count as a miss, writes are skipped, and both leave an event and a metric.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import telemetry
from app.core.logging import log_event
from app.domain.analysis import AnalysisResult
from app.domain.analysis_records import MATCH_TEXT, SAVED_QUERY_MAX_CHARS, ReusedMatch
from app.domain.models.saved_answer import SavedAnswer
from app.infrastructure.repositories.saved_answer_repository import (
    SavedAnswerRepository,
    SavedAnswerSummary,
)
from app.services.analysis import answer_cache, trace
from app.services.analysis.config import CacheSettings
from app.services.analysis.pipeline import ISTANBUL, Engine

logger = logging.getLogger("app.analysis")

LOOKUP_STEP = "Önceki cevap araması"


@dataclass(frozen=True, slots=True)
class Reuse:
    """An earlier answer given again, with what the record keeps about it."""

    result: AnalysisResult
    answered_at: datetime
    query: str
    match: ReusedMatch


def _failed(operation: str, error: BaseException) -> None:
    log_event(logger, "saved_answer.failed", operation=operation, error_type=type(error).__name__)


class SavedAnswers:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def lookup(
        self,
        tenant_id: int,
        engine: Engine,
        query: str,
        keys: tuple[str, str],
        fingerprint: str,
    ) -> Reuse | None:
        """Requirement 14: the newest usable answer, as the step "Önceki cevap araması" of the
        current trace. None for a miss, a disabled cache or a store failure."""

        c: CacheSettings = engine.settings.cache
        if not c.enabled:
            telemetry.record_saved_answer_lookup("disabled")
            return None
        started = time.perf_counter()
        with trace.span(LOOKUP_STEP, key="saved_answer_lookup") as step:
            try:
                found = await self._find(tenant_id, keys, fingerprint, c)
            except Exception as error:  # noqa: BLE001 - a store failure means "analyse again"
                _failed("lookup", error)
                telemetry.record_saved_answer_lookup("error")
                if step is not None:
                    step.detail = "yok"
                return None
            reuse = None
            if found is not None:
                row, match = found
                result = answer_cache.decode(row.result, engine.dictionary.by_key())
                if result is not None:
                    reuse = Reuse(result, row.answered_at, row.query_text, match)
            if step is not None:
                step.detail = (
                    f"{MATCH_TEXT[reuse.match]}: {reuse.query[:120]}"
                    if reuse is not None
                    else "yok"
                )
        telemetry.record_saved_answer_lookup(reuse.match.value if reuse else "miss")
        if reuse is None:
            return None
        _given_again(reuse, query, started)
        return reuse

    async def _find(
        self, tenant_id: int, keys: tuple[str, str], fingerprint: str, c: CacheSettings
    ) -> tuple[SavedAnswer, ReusedMatch] | None:
        text, meaning = keys
        since = self._clock() - timedelta(days=c.max_age_days) if c.max_age_days else None
        async with self._session_factory() as session:
            store = SavedAnswerRepository(session)
            row = await store.newest(tenant_id, fingerprint, since=since, text_key=text)
            if row is not None:
                return row, ReusedMatch.SAME_QUESTION
            if c.meaning and meaning:
                row = await store.newest(tenant_id, fingerprint, since=since, meaning_key=meaning)
                if row is not None:
                    return row, ReusedMatch.SAME_MEANING
        return None

    async def put(
        self,
        tenant_id: int,
        *,
        query: str,
        keys: tuple[str, str],
        fingerprint: str,
        result: AnalysisResult,
        analysis_public_id: str | None,
        user_id: int | None,
    ) -> bool:
        """Write an analyst answer; False (and an event) when the store fails."""

        try:
            async with self._session_factory() as session:
                await SavedAnswerRepository(session).put(
                    tenant_id,
                    query_text=query[:SAVED_QUERY_MAX_CHARS],
                    text_key=keys[0],
                    meaning_key=keys[1],
                    fingerprint=fingerprint,
                    result=answer_cache.encode(result),
                    answered_at=self._clock(),
                    analysis_public_id=analysis_public_id,
                    user_id=user_id,
                )
                await session.commit()
        except Exception as error:  # noqa: BLE001 - the answer matters more than keeping it
            _failed("write", error)
            telemetry.record_saved_answer_write("error")
            return False
        telemetry.record_saved_answer_write("stored")
        return True

    async def forget(self, tenant_id: int, text_key: str, meaning_key: str) -> int:
        """Requirement 15's internal service for answer-feedback: the rows of this question and
        of those meaning the same, whatever the fingerprint."""

        try:
            async with self._session_factory() as session:
                removed = await SavedAnswerRepository(session).forget(
                    tenant_id, text_key, meaning_key
                )
                await session.commit()
        except Exception as error:
            _failed("delete", error)
            raise
        return removed

    async def clear(self, tenant_id: int, actor_public_id: str) -> int:
        try:
            async with self._session_factory() as session:
                removed = await SavedAnswerRepository(session).clear(tenant_id)
                await session.commit()
        except Exception as error:
            _failed("delete", error)
            raise
        log_event(logger, "saved_answer.cleared", removed=removed, user_public_id=actor_public_id)
        return removed

    async def summary(self, tenant_id: int, fingerprint: str) -> SavedAnswerSummary:
        async with self._session_factory() as session:
            return await SavedAnswerRepository(session).summary(tenant_id, fingerprint)


def _given_again(reuse: Reuse, query: str, started: float) -> None:
    """The source's ``App._reuse``: the method line, ``reused_*`` and the lookup's duration."""

    result = reuse.result
    at = reuse.answered_at.astimezone(ISTANBUL).strftime("%d.%m.%Y %H:%M")
    match = MATCH_TEXT[reuse.match]
    first = "Bu soru" if reuse.match is ReusedMatch.SAME_QUESTION else (
        f"Aynı anlama gelen “{reuse.query}” sorusu")  # fmt: skip
    result.method = [
        (
            f"{first} {at} tarihinde analiz edildi ({result.elapsed_ms / 1000:.0f} sn); kayıtlı "
            "cevap yeniden kullanıldı (sözlük, model ve ayarlar aynı). Yeni bir analiz için "
            "“Yeniden analiz et”."
        ),
        *result.method,
    ]
    result.reused_at, result.reused_match = at, match
    result.reused_query = reuse.query
    result.query = query
    result.elapsed_ms = round((time.perf_counter() - started) * 1000)
