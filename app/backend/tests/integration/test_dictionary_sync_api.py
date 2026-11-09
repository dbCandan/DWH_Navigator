"""Dictionary update end to end on PostgreSQL with a fake source and model (011-dictionary-sync)."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.session import async_session_factory
from app.domain.dictionary_source import (
    SourceColumn,
    SourceProbe,
    SourceSnapshot,
    SourceTable,
    SourceUnavailable,
    TargetUnavailable,
)
from app.domain.llm import LlmConnection
from app.main import app
from app.services.dictionary_sync import DictionarySync
from tests.integration.data_dictionary import DataDictionary, error, sql
from tests.unit.analysis.workbooks import xlsx_bytes

pytestmark = pytest.mark.integration


def tables(*names: str, columns: int = 2, description: str = "Kolon açıklaması") -> SourceSnapshot:
    return SourceSnapshot(
        tables=tuple(SourceTable("EDWDM", "CUS", n, f"{n} tablosu") for n in names),
        columns=tuple(
            SourceColumn("EDWDM", "CUS", n, f"Kolon{i}", description, "Müşteri")
            for n in names
            for i in range(columns)
        ),
        skipped=0,
        excluded_tables=(),
        excluded_columns=(),
        corrected_tables=(),
        corrected_columns=(),
    )


@dataclass
class FakeSource:
    snapshot: SourceSnapshot = field(default_factory=lambda: tables("vParty"))
    failure: Exception | None = None
    gate: asyncio.Event | None = None

    async def probe(self, connection: Any) -> SourceProbe:
        return SourceProbe(table_count=1, column_count=2, last_change_at=None, missing_databases=())

    async def read(self, connection: Any) -> SourceSnapshot:
        if self.gate is not None:
            await self.gate.wait()
        if self.failure is not None:
            raise self.failure
        return self.snapshot


class FakeKeys:
    available = True

    def seal(self, password: str, **_: Any) -> str:
        return f"sealed:{password}"

    def open(self, row: Any, **_: Any) -> str | None:
        value = row.password_ciphertext
        return value.removeprefix("sealed:") if value else None


@dataclass
class FakePort:
    calls: int = 0
    down: bool = False  # every call fails, as when the model server is unreachable
    seen: list[tuple[str, str, str]] = field(default_factory=list)  # (model, reasoning, system)
    extra: dict[str, Any] = field(default_factory=dict)  # more fields in every answer

    async def chat(self, connection: Any, request: Any) -> Any:
        self.calls += 1
        self.seen.append((connection.chat_model, connection.reasoning_effort, request.system[:40]))
        if self.down:
            return SimpleNamespace(ok=False, value=None)
        return SimpleNamespace(
            ok=True,
            value={
                "table": {"Grain": "Müşteri"},
                "columns": [{"name": "Kolon0", "Role": "Anahtar"}],
                "terms": [],
                "stopwords": [],
                **self.extra,
            },
        )


@dataclass
class FakeGateway:
    port: FakePort = field(default_factory=FakePort)
    connection: LlmConnection = field(
        default_factory=lambda: LlmConnection(
            endpoint="http://model.test/v1", chat_model="test-model"
        )
    )

    async def snapshot(self, **_: Any) -> LlmConnection:
        return self.connection


@dataclass
class Harness:
    dd: DataDictionary
    source: FakeSource
    gateway: FakeGateway

    async def connect(self) -> None:
        response = await self.dd.request(
            "PUT",
            "/dictionary/source",
            json={
                "host": "dwh-source",
                "port": 1433,
                "database": "EDWUTIL",
                "username": "navigator",
                "password": "gizli-parola",
                "encrypt": False,
            },
        )
        assert response.status_code == 200, response.text
        assert "gizli-parola" not in response.text

    async def run(self) -> dict[str, Any]:
        response = await self.dd.request("POST", "/dictionary/sync")
        assert response.status_code == 202, response.text
        return await self.finished(response.json()["public_id"])

    async def finished(self, public_id: str) -> dict[str, Any]:
        for _ in range(400):
            run = (await self.dd.get(f"/dictionary/sync/runs/{public_id}")).json()
            if run["status"] != "running":
                return dict(run)
            await asyncio.sleep(0.02)
        raise AssertionError("the run did not end")

    async def active(self) -> tuple[str, int]:
        state = (await self.dd.get("/dictionary")).json()
        return state["active"]["version"], state["active"]["object_count"]


@pytest.fixture
async def sync(dd: DataDictionary) -> AsyncIterator[Harness]:
    source = FakeSource()
    gateway = FakeGateway()
    previous = getattr(app.state, "dictionary_sync", None)
    app.state.dictionary_sync = DictionarySync(
        index=dd.index,
        models=gateway,  # type: ignore[arg-type]
        source=source,
        keys=FakeKeys,  # type: ignore[arg-type]
        session_factory=async_session_factory,
    )
    harness = Harness(dd, source, gateway)
    await harness.connect()
    try:
        yield harness
    finally:
        await app.state.dictionary_sync.shutdown()
        app.state.dictionary_sync = previous


async def test_the_first_update_creates_the_active_version_and_its_report(sync: Harness) -> None:
    run = await sync.run()
    assert run["status"] == "completed", run
    assert run["counts"]["tables_added"] == 1
    assert run["counts"]["columns_added"] == 2
    assert run["counts"]["fields_filled"] >= 2
    assert run["model"] == "test-model"
    version, objects = await sync.active()
    assert version == run["new_version"]
    assert objects == 1
    assert sync.dd.index.serving is not None
    assert sync.dd.index.serving.engine.dictionary.version == version
    changes = (await sync.dd.get(f"/dictionary/sync/runs/{run['public_id']}/changes")).json()
    assert changes["total"] >= 1


async def test_an_unchanged_source_makes_no_version_and_no_model_call(sync: Harness) -> None:
    first = await sync.run()
    calls = sync.gateway.port.calls
    second = await sync.run()
    assert second["status"] == "no_change"
    assert sync.gateway.port.calls == calls
    assert (await sync.active())[0] == first["new_version"]


async def test_only_the_changed_table_reaches_the_model_and_filled_values_stay(
    sync: Harness,
) -> None:
    sync.source.snapshot = tables("vParty", "vOther", "vThird", "vFourth", "vFifth")
    await sync.run()
    sync.gateway.port.calls = 0
    grown = tables("vParty", "vOther", "vThird", "vFourth", "vFifth", "vSixth")
    sync.source.snapshot = grown
    run = await sync.run()
    assert run["status"] == "completed", run
    assert run["counts"]["tables_added"] == 1
    # The new table only: one fill call, one describe call per new column (two) and one for the
    # new object, and at most one suggestion call. The five unchanged tables add none.
    assert sync.gateway.port.calls <= 5
    table = (await sync.dd.get("/dictionary/tables/EDWDM.CUS.vParty")).json()
    assert table["object"]["Grain"] == "Müşteri"
    assert table["columns"][0]["Role"] == "Anahtar"


async def test_a_large_removal_waits_for_approval_and_can_be_approved(sync: Harness) -> None:
    sync.source.snapshot = tables("vA", "vB", "vC")
    first = await sync.run()
    sync.source.snapshot = tables("vA")
    run = await sync.run()
    assert run["status"] == "pending_approval"
    assert (await sync.active())[0] == first["new_version"]

    approved = await sync.dd.request("POST", f"/dictionary/sync/runs/{run['public_id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "completed"
    assert await sync.active() == (run["new_version"], 1)


async def test_a_rejected_version_never_becomes_active(sync: Harness) -> None:
    sync.source.snapshot = tables("vA", "vB", "vC")
    first = await sync.run()
    sync.source.snapshot = tables("vA")
    run = await sync.run()
    rejected = await sync.dd.request("POST", f"/dictionary/sync/runs/{run['public_id']}/reject")
    assert rejected.json()["status"] == "rejected"
    assert (await sync.active())[0] == first["new_version"]
    again = await sync.dd.request("POST", f"/dictionary/sync/runs/{run['public_id']}/approve")
    assert error(again) == (409, "dictionary_run_not_pending")


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (SourceUnavailable("network"), "dictionary_source_unavailable"),
        (TargetUnavailable(("EDWDM",)), "dictionary_target_unavailable"),
    ],
)
async def test_an_access_problem_fails_and_leaves_the_dictionary_alone(
    sync: Harness, failure: Exception, code: str
) -> None:
    first = await sync.run()
    sync.source.failure = failure
    run = await sync.run()
    assert run["status"] == "failed"
    assert run["error_code"] == code
    assert (await sync.active())[0] == first["new_version"]


async def test_an_empty_source_fails_instead_of_emptying_the_dictionary(sync: Harness) -> None:
    first = await sync.run()
    sync.source.snapshot = tables()
    run = await sync.run()
    assert run["status"] == "failed"
    assert (await sync.active())[0] == first["new_version"]


async def test_rollback_makes_a_new_active_version_and_keeps_history(sync: Harness) -> None:
    first = await sync.run()
    sync.source.snapshot = tables("vParty", columns=3)
    second = await sync.run()
    assert second["status"] == "completed"
    versions = (await sync.dd.get("/dictionary/versions")).json()["items"]
    old = next(v for v in versions if v["version"] == first["new_version"])
    assert old["can_restore"] is True
    assert old["expires_at"] is not None

    response = await sync.dd.request("POST", f"/dictionary/versions/{old['public_id']}/restore")
    assert response.status_code == 202, response.text
    run = await sync.finished(response.json()["public_id"])
    assert run["kind"] == "geri_donus"
    assert run["status"] == "completed", run
    assert (await sync.active())[0] == first["new_version"]
    after = (await sync.dd.get("/dictionary/versions")).json()["items"]
    assert len(after) == 3
    assert after[0]["channel"] == "geri_donus"
    assert sum(v["status"] == "active" for v in after) == 1


async def test_versions_older_than_a_month_are_pruned_and_cannot_be_restored(sync: Harness) -> None:
    first = await sync.run()
    sync.source.snapshot = tables("vParty", columns=3)
    await sync.run()
    versions = (await sync.dd.get("/dictionary/versions")).json()["items"]
    old = next(v for v in versions if v["version"] == first["new_version"])
    await sql(
        "UPDATE dictionary_version SET superseded_at = :t WHERE public_id = :p",
        t=datetime.now(UTC) - timedelta(days=31),
        p=old["public_id"],
    )
    sync.source.snapshot = tables("vParty", columns=4)
    await sync.run()
    response = await sync.dd.request("POST", f"/dictionary/versions/{old['public_id']}/restore")
    assert error(response) == (410, "dictionary_version_expired")
    rows = await sql(
        "SELECT count(*) FROM dictionary_column_record r JOIN dictionary_version v "
        "USING (dictionary_version_id) WHERE v.public_id = :p",
        p=old["public_id"],
    )
    assert rows[0][0] == 0


async def test_a_second_update_is_refused_while_one_runs(sync: Harness) -> None:
    sync.source.gate = asyncio.Event()
    started = await sync.dd.request("POST", "/dictionary/sync")
    assert started.status_code == 202
    second = await sync.dd.request("POST", "/dictionary/sync")
    assert error(second) == (409, "dictionary_sync_in_progress")
    sync.source.gate.set()
    await sync.finished(started.json()["public_id"])


async def test_an_update_needs_a_saved_connection(dd: DataDictionary, sync: Harness) -> None:
    await sql("DELETE FROM dictionary_source")
    response = await dd.request("POST", "/dictionary/sync")
    assert error(response) == (409, "dictionary_source_not_configured")


async def test_the_password_is_never_returned(sync: Harness) -> None:
    source = await sync.dd.get("/dictionary/source")
    assert source.json()["has_password"] is True
    assert "gizli" not in source.text


async def test_a_new_address_drops_the_saved_password(sync: Harness) -> None:
    response = await sync.dd.request(
        "PUT",
        "/dictionary/source",
        json={
            "host": "baska-sunucu",
            "port": 1433,
            "database": "EDWUTIL",
            "username": "navigator",
            "encrypt": False,
        },
    )
    assert response.json()["has_password"] is False


async def test_a_user_without_the_manager_role_cannot_start(sync: Harness) -> None:
    user = await sync.dd.auth.account(sync.dd.admin, "kullanici")
    response = await sync.dd.request("POST", "/dictionary/sync", user)
    assert response.status_code == 403


def with_code(snapshot: SourceSnapshot, factor: int, active: int = 1) -> SourceSnapshot:
    view = (
        "CREATE VIEW CUS.vParty AS SELECT P.Kolon0, P.Amount * {f} AS Kolon1 "
        "FROM EDW.CUS.Party P WHERE P.Active = {a}"
    )
    return replace(snapshot, code={"EDWDM.CUS.vParty": view.format(f=factor, a=active)})


async def test_only_a_changed_computation_comes_into_scope_and_no_change_means_no_model_call(
    sync: Harness,
) -> None:
    sync.source.snapshot = with_code(tables("vParty"), 100)
    await sync.run()
    calls = sync.gateway.port.calls
    same = await sync.run()
    assert same["status"] == "no_change"
    assert same["counts"]["scope_columns"] == 0
    assert sync.gateway.port.calls == calls
    # Reformatted code is the same computation.
    sync.source.snapshot = replace(
        sync.source.snapshot,
        code={
            k: v.replace(" SELECT ", "\n  SELECT\n    ")
            for k, v in sync.source.snapshot.code.items()
        },
    )
    assert (await sync.run())["counts"]["scope_columns"] == 0
    # The table came in new, so its trails were stored: a changed computation brings that column
    # only, also after runs that wrote no version, and it is described again.
    sync.source.snapshot = with_code(tables("vParty"), 1000)
    calls = sync.gateway.port.calls
    first = await sync.run()
    assert first["counts"]["scope_code_changed"] == 1
    assert sync.gateway.port.calls - calls >= 1
    sync.source.snapshot = with_code(tables("vParty"), 10000)
    calls = sync.gateway.port.calls
    changed = await sync.run()
    assert changed["counts"]["scope_code_changed"] == 1
    assert changed["counts"]["scope_columns"] == 1
    assert 1 <= sync.gateway.port.calls - calls <= 3
    # A changed filter of the object brings both of its columns.
    sync.source.snapshot = with_code(tables("vParty"), 10000, active=0)
    assert (await sync.run())["counts"]["scope_code_changed"] == 2


async def test_with_approval_an_update_waits_with_its_score_and_the_admin_text_survives(
    sync: Harness,
) -> None:
    await sync.run()  # the first dictionary goes live: there is nothing to compare it with
    app.state.dictionary_sync.requires_approval = True
    sync.source.snapshot = tables("vParty", "vOther")
    run = await sync.run()
    assert run["status"] == "pending_approval", run
    assert run["score"]["verdict"] in ("onaylanabilir", "incelenmeli", "reddedilmeli")
    assert "checks" in run["score"] and run["score"]["failed_checks"] == []
    path = f"/dictionary/sync/runs/{run['public_id']}/records"
    refused = await sync.dd.request(
        "PATCH",
        path,
        json={
            "table_key": "EDWDM.CUS.vOther",
            "column_name": "Kolon0",
            "field": "Role",
            "value": "Yok",
        },
    )
    assert refused.status_code == 422
    edited = await sync.dd.request(
        "PATCH",
        path,
        json={
            "table_key": "EDWDM.CUS.vOther",
            "column_name": "Kolon0",
            "field": "ColumnDescription",
            "value": "Yöneticinin yazdığı açıklama; iş birimi ile doğrulanmalıdır.",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["score"]["admin_edits"] == 1
    changes = (
        await sync.dd.get(
            f"/dictionary/sync/runs/{run['public_id']}/changes?kind=column_admin_edited"
        )
    ).json()
    assert changes["total"] == 1
    approved = await sync.dd.request("POST", f"/dictionary/sync/runs/{run['public_id']}/approve")
    assert approved.status_code == 200, approved.text
    version, _ = await sync.active()
    assert version == approved.json()["new_version"]

    def admin_text(table: dict[str, Any]) -> str:
        return next(c["ColumnDescription"] for c in table["columns"] if c["ColumnName"] == "Kolon0")

    text = "Yöneticinin yazdığı açıklama; iş birimi ile doğrulanmalıdır."
    assert admin_text((await sync.dd.get("/dictionary/tables/EDWDM.CUS.vOther")).json()) == text
    # A later update with a new source text neither overwrites nor cleans the admin's text.
    sync.source.snapshot = tables("vParty", "vOther", description="Yeni kaynak metni")
    later = await sync.run()
    assert later["status"] == "pending_approval"
    assert (
        await sync.dd.request("POST", f"/dictionary/sync/runs/{later['public_id']}/approve")
    ).status_code == 200
    assert admin_text((await sync.dd.get("/dictionary/tables/EDWDM.CUS.vOther")).json()) == text


async def test_only_a_waiting_version_can_be_edited(sync: Harness) -> None:
    run = await sync.run()
    response = await sync.dd.request(
        "PATCH",
        f"/dictionary/sync/runs/{run['public_id']}/records",
        json={
            "table_key": "EDWDM.CUS.vParty",
            "column_name": "Kolon0",
            "field": "Summary",
            "value": "x",
        },
    )
    assert response.status_code == 409


async def test_the_preview_counts_the_model_work_and_writes_nothing(sync: Harness) -> None:
    first = await sync.run()
    calls = sync.gateway.port.calls
    unchanged = (await sync.dd.get("/dictionary/sync/preview")).json()
    assert unchanged["has_changes"] is False and unchanged["model_calls"] == 0
    assert unchanged["estimated_seconds"] == 0
    sync.source.snapshot = tables("vParty", "vOther")
    grown = (await sync.dd.get("/dictionary/sync/preview")).json()
    assert grown["has_changes"] is True
    assert grown["rows_to_describe"] == 2 and grown["objects_to_describe"] == 1
    assert grown["model_calls"] >= 4 and grown["estimated_seconds"] > 0
    # Nothing was written and no model was called.
    assert sync.gateway.port.calls == calls
    assert (await sync.active())[0] == first["new_version"]


async def test_approved_admin_corrections_become_gold_set_rows(sync: Harness) -> None:
    from app.scripts.curation_feedback import collect

    await sync.run()
    app.state.dictionary_sync.requires_approval = True
    sync.source.snapshot = tables("vParty", "vOther")
    run = await sync.run()
    path = f"/dictionary/sync/runs/{run['public_id']}/records"
    body = {"table_key": "EDWDM.CUS.vOther", "column_name": "Kolon1", "field": "Summary"}
    assert (await sync.dd.request("PATCH", path, json={**body, "value": "İlk"})).status_code == 200
    assert (await sync.dd.request("PATCH", path, json={**body, "value": "Son"})).status_code == 200
    assert await collect(None) == []  # not approved yet
    assert (
        await sync.dd.request("POST", f"/dictionary/sync/runs/{run['public_id']}/approve")
    ).status_code == 200
    rows = await collect(None)
    assert [(r["obj"], r["col"], r["field"], r["gold_text"]) for r in rows] == [
        ("EDWDM.CUS.vOther", "Kolon1", "Summary", "Son")
    ]
    assert rows[0]["model_text"] != "İlk"  # the model's own text, not the admin's first try


async def test_a_text_the_rules_cleaned_does_not_come_back_from_the_same_source(
    sync: Harness,
) -> None:
    """Review: a cleaned source text bounced back on every run and made a version each time."""

    sync.source.snapshot = tables("vParty", description="Kredinin faiz oranıdır.")
    await sync.run()
    table = (await sync.dd.get("/dictionary/tables/EDWDM.CUS.vParty")).json()
    assert table["columns"][0]["ColumnDescription"] == "Fon kullandırımının kar payı oranıdır."
    again = await sync.run()
    assert again["status"] == "no_change", again
    # A new source text is taken, and cleaned in turn.
    sync.source.snapshot = tables("vParty", description="Mevduat faizidir.")
    changed = await sync.run()
    assert changed["status"] == "completed", changed
    table = (await sync.dd.get("/dictionary/tables/EDWDM.CUS.vParty")).json()
    assert table["columns"][0]["ColumnDescription"] == "Katılma hesabı kar payıdır."


async def test_a_changed_computation_the_model_did_not_answer_is_looked_at_again(
    sync: Harness,
) -> None:
    """Review: the trail digest was stored even when no row was described again."""

    sync.source.snapshot = with_code(tables("vParty"), 100)
    await sync.run()
    sync.source.snapshot = with_code(tables("vParty"), 1000)
    sync.gateway.port.down = True
    failed = await sync.run()
    assert failed["counts"]["scope_code_changed"] == 1
    sync.gateway.port.down = False
    again = await sync.run()
    assert again["counts"]["scope_code_changed"] == 1  # not lost
    assert (await sync.run())["counts"]["scope_code_changed"] == 0  # answered: settled


async def test_a_rejected_versions_digests_are_not_kept(sync: Harness) -> None:
    """Review: the digests of a rejected version made its code change look settled."""

    sync.source.snapshot = with_code(tables("vParty"), 100)
    await sync.run()
    app.state.dictionary_sync.requires_approval = True
    sync.source.snapshot = with_code(tables("vParty", "vOther"), 1000)
    waiting = await sync.run()
    assert waiting["status"] == "pending_approval" and waiting["counts"]["scope_code_changed"] == 1
    assert (
        await sync.dd.request("POST", f"/dictionary/sync/runs/{waiting['public_id']}/reject")
    ).status_code == 200
    again = await sync.run()
    assert again["counts"]["scope_code_changed"] == 1
    assert (
        await sync.dd.request("POST", f"/dictionary/sync/runs/{again['public_id']}/approve")
    ).status_code == 200
    sync.source.snapshot = with_code(tables("vParty", "vOther"), 1000)
    assert (await sync.run())["counts"]["scope_code_changed"] == 0


async def test_the_update_writes_with_the_dictionary_model_and_its_reasoning(sync: Harness) -> None:
    service = app.state.dictionary_sync
    service.chat_model, service.reasoning_effort, service.judge_reasoning_effort = (
        "qwen-test",
        "none",
        "low",
    )
    # The describer rewrites the new columns, so the verifier has texts of this run to score.
    sync.gateway.port.extra = {
        "karar": "eklendi",
        "ColumnDescription": "Müşteri kaydının kolonudur.",
        "aciklama": "dogru",
        "neden": "",
    }
    await sync.run()
    seen = sync.gateway.port.seen
    assert seen and all(model == "qwen-test" for model, _, _ in seen)
    judge = "Bir katılım bankası veri sözlüğünün"
    verifier = [effort for _, effort, system in seen if system.startswith(judge)]
    describer = [effort for _, effort, system in seen if not system.startswith(judge)]
    assert verifier and set(verifier) == {"low"}
    assert describer and set(describer) == {"none"}


async def test_the_ai_pages_generation_model_comes_before_the_environment(sync: Harness) -> None:
    service = app.state.dictionary_sync
    service.chat_model, service.reasoning_effort = "env-model", "medium"
    sync.gateway.connection = replace(
        sync.gateway.connection,
        generation_model="ai-page-model",
        generation_reasoning_effort="none",
        judge_reasoning_effort="inherit",
    )
    sync.gateway.port.extra = {
        "karar": "eklendi",
        "ColumnDescription": "Müşteri kaydının kolonudur.",
        "aciklama": "dogru",
        "neden": "",
    }
    service.judge_reasoning_effort = "low"
    await sync.run()
    seen = sync.gateway.port.seen
    assert {model for model, _, _ in seen} == {"ai-page-model"}
    judge = "Bir katılım bankası veri sözlüğünün"
    assert {effort for _, effort, system in seen if not system.startswith(judge)} == {"none"}
    # The verifier inherits on the AI page, so the environment's default applies.
    assert {effort for _, effort, system in seen if system.startswith(judge)} == {"low"}


async def test_the_run_passes_through_its_detailed_phases(sync: Harness) -> None:
    """The update window shows each step: describing and verifying with their counts."""

    seen: list[str] = []
    service = app.state.dictionary_sync
    original = service._set

    async def spy(run_id: int, **values: Any) -> None:
        if "phase" in values and (not seen or seen[-1] != values["phase"]):
            seen.append(values["phase"])
        await original(run_id, **values)

    service._set = spy
    sync.gateway.port.extra = {
        "karar": "eklendi",
        "ColumnDescription": "Müşteri kaydının kolonudur.",
        "aciklama": "dogru",
        "neden": "",
    }
    await sync.run()
    # "reading" is the phase the run opens with; the later ones follow in order.
    assert seen == ["comparing", "filling", "describing", "verifying", "scoring", "indexing"], seen


# --- the Excel import beside the update (dictionary-sync Requirement 13) -------------------------


def excel(*names: str, description: str = "Excel açıklaması") -> bytes:
    """A workbook in the template with the fake source's names."""

    columns = [
        {
            "DatabaseName": "EDWDM",
            "SchemaName": "CUS",
            "ObjectName": n,
            "ColumnName": f"Kolon{i}",
            "ColumnDescription": description,
            "Synonyms": "",
            "Role": "",
            "Summary": "",
        }
        for n in names
        for i in range(2)
    ]
    objects = [
        {"ObjectKey": f"EDWDM.CUS.{n}", "DatabaseName": "", "SchemaName": "", "ObjectName": "",
         "DatasetGroup": "Excel"}
        for n in names
    ]  # fmt: skip
    return xlsx_bytes({"Objeler": objects, "Kolonlar": columns})


async def test_an_excel_import_is_refused_while_an_update_runs(sync: Harness) -> None:
    sync.source.gate = asyncio.Event()
    started = await sync.dd.request("POST", "/dictionary/sync")
    assert started.status_code == 202
    refused = await sync.dd.import_dictionary(excel("vParty"))
    assert error(refused) == (409, "dictionary_sync_in_progress")
    assert refused.json()["detail"]["message"] == (
        "Bir sözlük güncellemesi sürüyor; bitince yeniden deneyin."
    )
    sync.source.gate.set()
    run = await sync.finished(started.json()["public_id"])
    assert run["status"] == "completed"
    assert (await sync.active())[0] == run["new_version"]


async def test_an_excel_import_drops_an_update_waiting_for_approval(sync: Harness) -> None:
    sync.source.snapshot = tables("vA", "vB", "vC")
    await sync.run()
    sync.source.snapshot = tables("vA")
    waiting = await sync.run()
    assert waiting["status"] == "pending_approval"

    imported = await sync.dd.import_dictionary(excel("vA", "vB"), name="elle.xlsx")
    assert imported.status_code == 201, imported.text
    assert await sync.active() == (imported.json()["version"]["version"], 2)
    run = (await sync.dd.get(f"/dictionary/sync/runs/{waiting['public_id']}")).json()
    assert run["status"] == "rejected"
    approve = await sync.dd.request("POST", f"/dictionary/sync/runs/{waiting['public_id']}/approve")
    assert error(approve) == (409, "dictionary_run_not_pending")
    rows = await sql("SELECT count(*) FROM dictionary_version WHERE status = 'pending'")
    assert rows[0][0] == 0


async def test_an_update_after_an_excel_import_keeps_the_imported_texts(sync: Harness) -> None:
    imported = await sync.dd.import_dictionary(excel("vParty"))
    assert imported.status_code == 201, imported.text
    run = await sync.run()
    assert run["status"] in ("completed", "no_change"), run
    table = (await sync.dd.get("/dictionary/tables/EDWDM.CUS.vParty")).json()
    assert [c["ColumnDescription"] for c in table["columns"]] == ["Excel açıklaması"] * 2
    assert table["object"]["DatasetGroup"] == "Excel"
