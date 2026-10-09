"""The word lists on PostgreSQL (vocabulary-management Acceptance 2).

Requirement 1 (lists and revision), 5 (all or nothing with the index, same content, the later save
wins), 7-8 (Excel import), 9 (the seed migration's three cases), 14 (the engine uses the new list)
and 15 (roles).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import engine
from app.infrastructure.excel.writer import workbook_bytes
from tests.integration.conftest import RecordingHandler
from tests.integration.data_dictionary import (
    DataDictionary,
    error,
    first_then,
    run_seed,
    sql,
    started_index,
)

pytestmark = pytest.mark.integration

SEED = Path(__file__).resolve().parents[4] / "schema" / "alembic" / "seed" / "vocabulary"
NEW_GROUP = {"term": "zırhlı araç", "equivalents": ["panzer", "tank"], "domain": "test", "note": ""}


async def current(table: str) -> int:
    (count,) = (await sql(f"SELECT count(*) FROM {table} WHERE NOT is_deleted"))[0]
    return int(count)


async def header(name: str) -> tuple[int, str, Any]:
    row = (
        await sql(
            "SELECT revision, last_source, updated_by FROM vocabulary_list WHERE public_id = :n",
            n=name,
        )
    )[0]
    return int(row[0]), str(row[1]), row[2]


async def test_every_endpoint_needs_a_session_and_the_manager_role(dd: DataDictionary) -> None:
    user = await dd.auth.account(dd.admin, "kullanici")
    xlsx = {"content": b"x", "headers": {"Content-Type": "application/octet-stream"}}
    calls = [
        ("GET", "/vocabulary/terms", {}),
        ("PUT", "/vocabulary/stopwords", {"json": {"items": []}}),
        ("GET", "/vocabulary/terms/export", {}),
        ("POST", "/vocabulary/stopwords/import", xlsx),
    ]
    for method, path, kwargs in calls:
        anonymous = await dd.auth.client.request(
            method,
            dd.url(path),
            headers={dd.auth.settings.tenant_header: dd.manager.tenant_id},
            **{k: v for k, v in kwargs.items() if k != "headers"},
        )
        assert error(anonymous) == (401, "not_authenticated"), path
        assert error(await dd.request(method, path, user, **kwargs)) == (403, "forbidden"), path
    assert error(await dd.get("/vocabulary/kelimeler")) == (404, "vocabulary_list_not_found")
    assert (await dd.get("/vocabulary/terms", dd.admin)).status_code == 200


async def test_the_seed_lists_are_there_from_the_start(dd: DataDictionary) -> None:
    terms = (await dd.get("/vocabulary/terms")).json()
    words = (await dd.get("/vocabulary/stopwords")).json()
    assert (terms["list"], terms["revision"], len(terms["items"])) == ("terms", 1, 45)
    assert (words["list"], words["revision"], len(words["items"])) == ("stopwords", 1, 106)
    seed = [json.loads(line) for line in (SEED / "terms.jsonl").read_text("utf-8").splitlines()]
    assert terms["items"] == seed
    assert await header("terms") == (1, "baslangic", None)
    engine_groups = dd.index.engine().resources.term_groups
    assert len(engine_groups) == 45 and len(dd.index.engine().resources.stopwords) == 124


async def test_a_save_builds_the_index_then_writes_the_list(dd: DataDictionary) -> None:
    items = (await dd.get("/vocabulary/terms")).json()["items"]
    old_engine = dd.index.engine()
    response = await dd.put_list("terms", [NEW_GROUP, *items])
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["list"], body["revision"], body["changed"]) == ("terms", 2, True)
    assert body["items"][0] == NEW_GROUP and len(body["items"]) == 46
    assert body["elapsed_ms"] >= 0 and body["index"]["trigger"] == "terms"
    assert body["index"]["state"] == "ready"
    revision, source, updated_by = await header("terms")
    assert (revision, source) == (2, "ekran") and updated_by is not None
    assert await current("vocabulary_term") == 46
    (deleted,) = (await sql("SELECT count(*) FROM vocabulary_term WHERE is_deleted"))[0]
    assert deleted == 45  # the old rows are kept soft-deleted and never read
    groups = dd.index.engine().resources.term_groups
    assert groups[0].term == "zırhlı araç" and groups[0].equivalents == ("panzer", "tank")
    assert dd.index.engine().bm25 is old_engine.bm25  # terms are not in the word index
    assert old_engine.resources.term_groups[0].term == "fon kullandırım"

    again = await dd.put_list("terms", body["items"])
    assert again.json()["changed"] is False and again.json()["revision"] == 2
    assert await current("vocabulary_term") == 46


async def test_the_first_stopword_save_folds_the_seed_to_104(dd: DataDictionary) -> None:
    words = (await dd.get("/vocabulary/stopwords")).json()["items"]
    forms = dd.index.engine().resources.stopwords
    response = await dd.put_list("stopwords", words)
    assert response.json()["changed"] is True and len(response.json()["items"]) == 104
    assert dd.index.engine().resources.stopwords == forms  # the same 124 forms
    assert response.json()["revision"] == 2


async def test_refused_lists_change_nothing(
    dd: DataDictionary, recorded_logs: RecordingHandler
) -> None:
    serving = dd.index.serving
    cases = [
        ("terms", "değil", (422, "vocabulary_items_invalid")),
        ("terms", [{"term": "x"}], (422, "vocabulary_term_without_equivalents")),
        ("terms", [{"term": 3, "equivalents": ["a"]}], (422, "invalid_request")),
        ("stopwords", [{"word": "iki kelime"}], (422, "vocabulary_stopword_not_single_word")),
    ]
    for kind, items, expected in cases:
        assert error(await dd.put_list(kind, items)) == expected
    assert (await current("vocabulary_term"), await current("vocabulary_stopword")) == (45, 106)
    assert await header("terms") == (1, "baslangic", None)
    assert dd.index.serving is serving
    assert [e["code"] for e in recorded_logs.events("vocabulary.rejected")] == [
        "vocabulary_items_invalid",
        "vocabulary_term_without_equivalents",
        "invalid_request",
        "vocabulary_stopword_not_single_word",
    ]


async def test_a_failed_build_keeps_the_list_and_the_engine(dd: DataDictionary) -> None:
    def broken(*_: Any) -> Any:
        raise RuntimeError("x")

    dd.use_index(await started_index(builder=first_then(broken)))
    serving = dd.index.serving
    response = await dd.put_list("stopwords", [{"word": "ve"}])
    assert error(response) == (500, "search_index_build_failed")
    assert await current("vocabulary_stopword") == 106 and dd.index.serving is serving
    assert await header("stopwords") == (1, "baslangic", None)


async def test_two_saves_one_after_the_other_the_later_wins(dd: DataDictionary) -> None:
    other = await dd.auth.account(dd.admin, "yonetici")
    first = await dd.put_list("stopwords", [{"word": "bir", "group": "A"}])
    second = await dd.put_list("stopwords", [{"word": "iki", "group": "B"}], who=other)
    assert first.json()["revision"] == 2 and second.json()["revision"] == 3
    assert (await dd.get("/vocabulary/stopwords")).json()["items"] == [
        {"word": "iki", "group": "B"}
    ]
    assert "iki" in dd.index.engine().resources.stopwords
    assert "bir" not in dd.index.engine().resources.stopwords


def _workbook(title: str, rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    return workbook_bytes(book)


async def test_lists_go_to_excel_and_come_back(dd: DataDictionary) -> None:
    exported = await dd.get("/vocabulary/terms/export")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].startswith('attachment; filename="TerimSozlugu_')
    same = await dd.upload("/vocabulary/terms/import", exported.content, name="liste.xlsx")
    assert same.status_code == 200 and same.json()["changed"] is False
    edited = _workbook(
        "Terimler",
        [["Terim", "Eşdeğerler", "Alan", "Not"], ["zırhlı araç", "panzer; tank", "test", None]],
    )
    replaced = await dd.upload("/vocabulary/terms/import", edited)
    assert replaced.json()["changed"] is True and replaced.json()["items"] == [NEW_GROUP]
    revision, source, updated_by = await header("terms")
    assert (revision, source) == (2, "excel") and updated_by is not None
    words = await dd.get("/vocabulary/stopwords/export")
    assert 'filename="DurakKelimeler_' in words.headers["content-disposition"]


async def test_workbook_refusals_change_nothing(dd: DataDictionary) -> None:
    cases = [
        (b"", (422, "vocabulary_file_empty")),
        (b"not excel", (422, "vocabulary_workbook_unreadable")),
        (
            _workbook("DurakKelimeler", [["Grup"], ["g"]]),
            (422, "vocabulary_workbook_column_missing"),
        ),
        (_workbook("DurakKelimeler", [["Kelime"], [None]]), (422, "vocabulary_workbook_empty")),
        (
            _workbook("DurakKelimeler", [["Kelime"], *[[f"k{i}"] for i in range(5001)]]),
            (422, "vocabulary_workbook_too_many_rows"),
        ),
        (
            _workbook("DurakKelimeler", [["Kelime"], ["iki kelime"]]),
            (422, "vocabulary_stopword_not_single_word"),
        ),
    ]
    for data, expected in cases:
        assert error(await dd.upload("/vocabulary/stopwords/import", data)) == expected
    assert error(
        await dd.upload("/vocabulary/stopwords/import", b"x", media_type="application/json")
    ) == (415, "unsupported_media_type")
    assert await current("vocabulary_stopword") == 106


# --- Requirement 9: the seed migration ----------------------------------------------------------


async def test_the_seed_runs_once_and_refuses_a_changed_copy(
    dd: DataDictionary, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="alembic.runtime.migration.vocabulary")
    # A list header exists, even of an emptied list: nothing is written.
    assert (await dd.put_list("stopwords", [])).json()["items"] == []
    async with engine.begin() as connection:
        await connection.run_sync(run_seed)
    assert await current("vocabulary_stopword") == 0 and await current("vocabulary_term") == 45
    assert "vocabulary.seed" in caplog.text and '"outcome": "skipped"' in caplog.text

    # A seed copy that differs from the recorded digest stops the migration.
    changed = tmp_path / "seed"
    changed.mkdir()
    for name in ("terms.jsonl", "stopwords.jsonl"):
        (changed / name).write_bytes((SEED / name).read_bytes() + b"\n")
    await sql("DELETE FROM vocabulary_stopword")
    await sql("DELETE FROM vocabulary_list WHERE public_id = 'stopwords'")
    with pytest.raises(RuntimeError, match="does not match"):
        async with engine.begin() as connection:
            await connection.run_sync(lambda c: run_seed(c, changed))
    assert '"outcome": "failed"' in caplog.text

    # An empty database gets both lists as they are.
    async with engine.begin() as connection:
        await connection.run_sync(run_seed)
    assert (await current("vocabulary_term"), await current("vocabulary_stopword")) == (45, 106)
    assert await header("stopwords") == (1, "baslangic", None)
    (folded,) = (
        await sql("SELECT count(DISTINCT word_key) FROM vocabulary_stopword WHERE NOT is_deleted")
    )[0]
    assert folded == 104  # mi/mı and mu/mü stay in separate rows


async def test_the_database_keeps_terms_unique_and_positions_ordered(dd: DataDictionary) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("BEGIN"))
        with pytest.raises(DBAPIError):
            await connection.execute(
                text(
                    "INSERT INTO vocabulary_term (tenant_id, vocabulary_list_id, position, term, "
                    "term_key, equivalents) SELECT tenant_id, vocabulary_list_id, 999, 'X', "
                    "term_key, '{a}' FROM vocabulary_term WHERE position = 0"
                )
            )
        await connection.execute(text("ROLLBACK"))
