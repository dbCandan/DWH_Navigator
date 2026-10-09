"""Saved answers in PostgreSQL (data-dictionary/PRDs/004-question-analysis Requirement 13-15,
Acceptance 4): the same question first, then the same meaning, within the age limit and the
fingerprint; rebuilt with the current dictionary; the newest 2000; replaced per question and
fingerprint; forgotten by question or meaning; a store failure never stops an analysis."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.db.session import async_session_factory
from app.domain.analysis_records import ReusedMatch
from app.services.analysis.pipeline import Engine
from app.services.analysis.saved_answers import SavedAnswers
from app.services.search_index import IndexTrigger, build_engine
from app.services.search_inputs import read_inputs
from tests.integration.conftest import RecordingHandler
from tests.integration.data_dictionary import SYNTHETIC_WORKBOOK, DataDictionary, sql
from tests.parity.fake_model import FakeAnalyst
from tests.parity.run_target import TargetClient

pytestmark = pytest.mark.integration

FP = "0123456789abcdef"


@pytest.fixture
async def engine(dd: DataDictionary) -> AsyncIterator[Engine]:
    await sql("DELETE FROM saved_answer")
    imported = await dd.import_dictionary(SYNTHETIC_WORKBOOK.read_bytes())
    assert imported.status_code in (200, 201), imported.text
    inputs = await read_inputs(async_session_factory, await dd.index.tenant_id())
    yield build_engine(inputs, None, IndexTrigger.STARTUP)


async def tenant() -> int:
    ((value,),) = await sql("SELECT tenant_id FROM tenant WHERE code = 'platform'")
    return int(value)


def answer(engine: Engine, query: str) -> Any:
    core = FakeAnalyst()
    core.begin(query, "normal")
    result = engine.with_llm(TargetClient(core)).analyze(query, 5)
    assert result.analyst and result.objects
    return result


async def put(store: SavedAnswers, engine: Engine, query: str, fp: str = FP) -> None:
    keys = engine.cache_keys(query)
    assert await store.put(
        await tenant(),
        query=query,
        keys=keys,
        fingerprint=fp,
        result=answer(engine, query),
        analysis_public_id=None,
        user_id=None,
    )


async def lookup(store: SavedAnswers, engine: Engine, query: str, fp: str = FP) -> Any:
    return await store.lookup(await tenant(), engine, query, engine.cache_keys(query), fp)


async def test_the_same_question_then_the_same_meaning(engine: Engine) -> None:
    store = SavedAnswers(async_session_factory)
    await put(store, engine, "Kredi kartı limit doluluk oranı")
    same = await lookup(store, engine, "kredi KARTI limit doluluk oranı?")
    assert same is not None and same.match is ReusedMatch.SAME_QUESTION
    assert same.result.reused_match == "aynı soru"
    assert same.result.query == "kredi KARTI limit doluluk oranı?"
    assert same.result.method[0].startswith("Bu soru ")
    assert await lookup(store, engine, "Kredi kartı limit doluluk oranı", fp="f" * 16) is None
    meaning = engine.cache_keys("Kredi kartı limit doluluk oranı nedir")[1]
    assert meaning == engine.cache_keys("Kredi kartı limit doluluk oranı")[1]
    other = await lookup(store, engine, "Kredi kartı limit doluluk oranı nedir")
    assert other is not None and other.match is ReusedMatch.SAME_MEANING
    assert other.result.method[0].startswith("Aynı anlama gelen “Kredi kartı limit doluluk oranı”")
    engine.settings.cache.meaning = False
    assert await lookup(store, engine, "Kredi kartı limit doluluk oranı nedir") is None
    engine.settings.cache.enabled = False
    assert await lookup(store, engine, "Kredi kartı limit doluluk oranı") is None


async def test_age_limit_replacement_and_the_newest_2000(engine: Engine) -> None:
    store = SavedAnswers(async_session_factory)
    await put(store, engine, "Müşterinin kredi risk skoru")
    await put(store, engine, "Müşterinin kredi risk skoru")
    assert await sql("SELECT count(*) FROM saved_answer") == [(1,)]
    await sql("UPDATE saved_answer SET answered_at = now() - interval '31 days'")
    assert await lookup(store, engine, "Müşterinin kredi risk skoru") is None
    engine.settings.cache.max_age_days = 0
    assert await lookup(store, engine, "Müşterinin kredi risk skoru") is not None
    t = await tenant()
    await sql(
        "INSERT INTO saved_answer (public_id, tenant_id, query_text, text_key, meaning_key, "
        "fingerprint, result, answered_at) SELECT gen_random_uuid()::text, :t, 'q' || n, "
        "'q' || n, '', :fp, '{}'::jsonb, now() - interval '1 day' + n * interval '1 second' "
        "FROM generate_series(1, 2000) n",
        t=t,
        fp=FP,
    )
    await put(store, engine, "Kredi kartı limit doluluk oranı")
    assert await sql("SELECT count(*) FROM saved_answer") == [(2000,)]
    assert await sql(
        "SELECT count(*) FROM saved_answer WHERE text_key = 'musterinin kredi risk skoru'"
    ) == [(0,)]
    assert await sql("SELECT count(*) FROM saved_answer WHERE text_key = 'q1'") == [(0,)]


async def test_an_answer_whose_column_is_gone_is_not_given(engine: Engine) -> None:
    store = SavedAnswers(async_session_factory)
    await put(store, engine, "Müşterinin kredi risk skoru")
    ((result,),) = await sql("SELECT result FROM saved_answer")
    result["objects"][0]["columns"][0]["col"] = "DB.dbo.yok.Kolon"
    await sql("UPDATE saved_answer SET result = CAST(:r AS jsonb)", r=json.dumps(result))
    assert await lookup(store, engine, "Müşterinin kredi risk skoru") is None


async def test_forget_and_clear(engine: Engine) -> None:
    store = SavedAnswers(async_session_factory)
    await put(store, engine, "Kredi kartı limit doluluk oranı")
    await put(store, engine, "Kredi kartı limit doluluk oranı nedir", fp="f" * 16)
    await put(store, engine, "Müşterinin kredi risk skoru")
    keys = engine.cache_keys("Kredi kartı limit doluluk oranı")
    assert await store.forget(await tenant(), *keys) == 2
    assert await store.forget(await tenant(), *keys) == 0
    assert await store.clear(await tenant(), "kisi") == 1
    assert await store.clear(await tenant(), "kisi") == 0


async def test_a_store_failure_is_a_miss_and_a_skipped_write(
    engine: Engine, recorded_logs: RecordingHandler
) -> None:
    logging.getLogger("app.analysis").setLevel(logging.INFO)

    def broken() -> Any:
        raise ConnectionError("veritabanı yok")

    store = SavedAnswers(broken)  # type: ignore[arg-type]
    assert await lookup(store, engine, "Müşterinin kredi risk skoru") is None
    keys = engine.cache_keys("Müşterinin kredi risk skoru")
    assert not await store.put(
        await tenant(),
        query="Müşterinin kredi risk skoru",
        keys=keys,
        fingerprint=FP,
        result=answer(engine, "Müşterinin kredi risk skoru"),
        analysis_public_id=None,
        user_id=None,
    )
    events = recorded_logs.events("saved_answer.failed")
    assert [(e["operation"], e["error_type"]) for e in events] == [
        ("lookup", "ConnectionError"),
        ("write", "ConnectionError"),
    ]
    assert "veritabanı yok" not in recorded_logs.rendered()
