"""The rules that protect dictionary content during an update (011-dictionary-sync)."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.domain.dictionary_source import SourceColumn, SourceSnapshot, SourceTable
from app.domain.llm import LlmChatRequest
from app.services.analysis.dictionary_workbook import COLUMN_FIELDS, OBJECT_FIELDS
from app.services.dictionary_sync_describe import describe_tables
from app.services.dictionary_sync_fill import (
    COLUMN_TEXT_MAX,
    candidates,
    fill_tables,
    name_tokens,
    suggest,
    valid_description,
)
from app.services.dictionary_sync_merge import (
    ORIGIN_EDITED,
    ORIGIN_MODEL,
    merge,
    pick,
    source_digest,
    without_marking,
)

KEY = "EDWDM.CUS.vParty"


def table(name: str = "vParty", description: str = "Kaynak tablo") -> SourceTable:
    return SourceTable("EDWDM", "CUS", name, description)


def column(name: str, description: str = "Kaynak kolon", group: str = "Müşteri") -> SourceColumn:
    return SourceColumn("EDWDM", "CUS", "vParty", name, description, group)


def snapshot(
    tables: tuple[SourceTable, ...],
    columns: tuple[SourceColumn, ...],
    **extra: Any,
) -> SourceSnapshot:
    values: dict[str, Any] = {
        "skipped": 0,
        "excluded_tables": (),
        "excluded_columns": (),
        "corrected_tables": (),
        "corrected_columns": (),
        **extra,
    }
    return SourceSnapshot(tables=tables, columns=columns, **values)


def prior_object(**fields: str) -> dict[str, str]:
    base = {f: "" for f in OBJECT_FIELDS}
    base.update(
        ObjectKey=KEY, DatabaseName="EDWDM", SchemaName="CUS", ObjectName="vParty", **fields
    )
    return base


def prior_column(name: str, **fields: str) -> dict[str, str]:
    base = {f: "" for f in COLUMN_FIELDS}
    base.update(
        DatabaseName="EDWDM", SchemaName="CUS", ObjectName="vParty", ColumnName=name, **fields
    )
    return base


def kinds(plan: Any) -> list[str]:
    return [c.kind for c in plan.changes]


def test_a_filled_value_never_gives_way_to_empty_or_foreign_source_text() -> None:
    assert pick("Elle yazılmış", "", "") == ("Elle yazılmış", "onceki")
    assert pick("Elle yazılmış", "onceki", "Kaynak") == ("Elle yazılmış", "onceki")
    assert pick("Model yazdı", "model", "Kaynak") == ("Model yazdı", "model")


def test_a_value_the_source_gave_follows_the_source() -> None:
    assert pick("Eski", "kaynak", "Yeni") == ("Yeni", "kaynak")
    assert pick("", "", "Yeni") == ("Yeni", "kaynak")


def test_merge_keeps_filled_fields_and_reports_nothing_when_nothing_changed() -> None:
    plan = merge(
        snapshot((table(),), (column("PartyId"),)),
        [prior_object(ObjectDescription="Elle", Grain="Müşteri", DatasetGroup="Grup")],
        [],
        [prior_column("PartyId", ColumnDescription="Elle", Role="Anahtar", Summary="Özet")],
        [],
    )
    merged = plan.tables[0]
    assert merged.record["ObjectDescription"] == "Elle"
    assert merged.record["Grain"] == "Müşteri"
    assert merged.columns[0].record["Role"] == "Anahtar"
    assert merged.needs_model is False
    assert plan.has_changes is False


def test_new_table_and_new_column_go_to_the_model_unchanged_ones_do_not() -> None:
    columns = (column("PartyId"),)
    digest = source_digest("Kaynak tablo", "Müşteri", columns)
    same = merge(
        snapshot((table(),), columns),
        [prior_object(ObjectDescription="Kaynak tablo", DatasetGroup="Müşteri")],
        [{"source_digest": digest}],
        [prior_column("PartyId", ColumnDescription="Kaynak kolon")],
        [],
    )
    assert same.tables[0].needs_model is False

    grown = merge(
        snapshot((table(),), (*columns, column("Segment"))),
        [prior_object(ObjectDescription="Kaynak tablo", DatasetGroup="Müşteri")],
        [{"source_digest": digest}],
        [prior_column("PartyId", ColumnDescription="Kaynak kolon")],
        [],
    )
    assert grown.tables[0].needs_model is True
    assert "column_added" in kinds(grown)


def test_a_failed_model_table_is_tried_again() -> None:
    columns = (column("PartyId"),)
    digest = source_digest("Kaynak tablo", "Müşteri", columns)
    plan = merge(
        snapshot((table(),), columns),
        [prior_object(ObjectDescription="Kaynak tablo", DatasetGroup="Müşteri")],
        [{"source_digest": digest, "model_pending": True}],
        [prior_column("PartyId", ColumnDescription="Kaynak kolon")],
        [],
    )
    assert plan.tables[0].needs_model is True


def test_a_table_missing_from_the_source_counts_toward_the_removal_limit() -> None:
    other = prior_object()
    other.update(ObjectKey="EDWDM.CUS.vGone", ObjectName="vGone")
    gone = prior_column("Old")
    gone["ObjectName"] = "vGone"
    plan = merge(
        snapshot((table(),), (column("PartyId"),)),
        [prior_object(), other],
        [],
        [prior_column("PartyId"), gone],
        [],
    )
    assert plan.removed_tables == 1
    assert plan.removed_columns == 1
    assert plan.removal_share() == 0.5
    assert "table_removed" in kinds(plan)


def test_excluded_records_stay_out_and_appear_in_the_report_only() -> None:
    plan = merge(
        snapshot(
            (table(),),
            (column("PartyId"),),
            excluded_tables=("EDWDM.CUS.vNowhere",),
            excluded_columns=((KEY, "Ghost"),),
        ),
        [],
        [],
        [],
        [],
    )
    assert [t.key for t in plan.tables] == [KEY]
    assert [c.record["ColumnName"] for c in plan.tables[0].columns] == ["PartyId"]
    assert {"table_excluded", "column_excluded"} <= set(kinds(plan))


def test_only_excluded_or_corrected_lines_create_no_version() -> None:
    plan = merge(
        snapshot(
            (table(),),
            (column("PartyId"),),
            excluded_tables=("EDWDM.CUS.vNowhere",),
            corrected_tables=(("EDWDM.CUS.vParty ", KEY),),
        ),
        [prior_object(ObjectDescription="Elle", DatasetGroup="Grup")],
        [],
        [prior_column("PartyId", ColumnDescription="Elle")],
        [],
    )
    assert plan.has_changes is False


def test_values_under_a_misspelled_name_move_to_the_real_name() -> None:
    wrong_key = "EDWDM.CUS.vParrty"
    prior = prior_object(Grain="Müşteri")
    prior.update(ObjectKey=wrong_key, ObjectName="vParrty")
    wrong_column = prior_column("PartyIdd", Role="Anahtar")
    wrong_column["ObjectName"] = "vParrty"
    plan = merge(
        snapshot(
            (table(),),
            (column("PartyId"),),
            corrected_tables=((wrong_key, KEY),),
            corrected_columns=((KEY, "PartyIdd", "PartyId"),),
        ),
        [prior],
        [],
        [wrong_column],
        [],
    )
    merged = plan.tables[0]
    assert merged.record["ObjectName"] == "vParty"
    assert merged.record["Grain"] == "Müşteri"
    assert merged.columns[0].record["ColumnName"] == "PartyId"
    assert merged.columns[0].record["Role"] == "Anahtar"
    assert plan.removed_tables == 0
    assert plan.removed_columns == 0


def test_load_dates_do_not_change_the_digest_but_a_description_does() -> None:
    columns = (column("PartyId"),)
    assert source_digest("A", "G", columns) == source_digest("A", "G", columns)
    assert source_digest("A", "G", columns) != source_digest("B", "G", columns)


@dataclass
class FakeResult:
    value: dict[str, Any] | None
    ok: bool = True


@dataclass
class FakeModel:
    value: dict[str, Any] | None
    ok: bool = True
    requests: list[LlmChatRequest] = field(default_factory=list)

    async def __call__(self, request: LlmChatRequest) -> Any:
        self.requests.append(request)
        return FakeResult(self.value, self.ok)


async def _no_progress(_done: int, _total: int) -> None:
    return None


def _new_table(*names: str) -> Any:
    plan = merge(snapshot((table(),), tuple(column(n, "") for n in names)), [], [], [], [])
    return plan.tables


def test_model_values_are_checked_and_cannot_add_columns() -> None:
    tables = _new_table("PartyId", "Segment")
    model = FakeModel(
        {
            "table": {
                "Grain": "Müşteri",
                "KeyColumns": "PartyId, Uydurma",
                "TimeColumns": "Segment",
            },
            "columns": [
                {"name": "PartyId", "Role": "Anahtar", "Summary": "x" * 71},
                {"name": "Segment", "Role": "Sihir", "Synonyms": "segment, kesim"},
                {"name": "Uydurma", "Role": "Kod"},
            ],
        }
    )
    outcome = asyncio.run(fill_tables(tables, model, _no_progress))
    merged = tables[0]
    assert merged.record["Grain"] == "Müşteri"
    assert merged.origins["Grain"] == ORIGIN_MODEL
    assert merged.record["KeyColumns"] == ""
    assert merged.record["TimeColumns"] == "Segment"
    party, segment = merged.columns
    assert party.record["Role"] == "Anahtar"
    assert party.record["Summary"] == ""
    assert segment.record["Role"] == ""
    assert segment.record["Synonyms"] == "segment, kesim"
    assert len(merged.columns) == 2
    assert outcome.warnings


def test_model_never_overwrites_a_filled_value() -> None:
    plan = merge(
        snapshot((table(),), (column("PartyId", ""),)),
        [],
        [],
        [],
        [],
    )
    merged = plan.tables[0]
    merged.columns[0].record["Role"] = "Kod"
    model = FakeModel({"columns": [{"name": "PartyId", "Role": "Anahtar"}]})
    asyncio.run(fill_tables(plan.tables, model, _no_progress))
    assert merged.columns[0].record["Role"] == "Kod"


def test_a_failed_call_keeps_the_table_pending_and_the_values_empty() -> None:
    tables = _new_table("PartyId")
    outcome = asyncio.run(fill_tables(tables, FakeModel(None, ok=False), _no_progress))
    assert tables[0].needs_model is True
    assert tables[0].object_meta["model_pending"] is True
    assert outcome.failures == 1


def test_a_new_rows_description_takes_the_target_form_and_keeps_the_original() -> None:
    plan = merge(snapshot((table(),), (column("PartyId", "Müşteri no"),)), [], [], [], [])
    model = FakeModel(
        {
            "ObjectDescription": "Müşteri: kimlik ve segment bilgileri.",
            "ColumnDescription": "Müşteri numarası.",
            "Summary": "Müşteri no",
            "karar": "eklendi",
        }
    )
    asyncio.run(describe_tables(plan.tables, model))
    merged = plan.tables[0]
    assert merged.columns[0].record["ColumnDescription"] == "Müşteri numarası."
    assert merged.columns[0].origins["ColumnDescription"] == ORIGIN_EDITED
    assert plan.column_meta()[0]["description_before"] == "Müşteri no"
    assert merged.object_meta["description_before"] == "Kaynak tablo"


def test_a_description_call_carries_every_context_and_only_its_own_evidence() -> None:
    plan = merge(
        snapshot((table(),), (column("PartyId", "Müşteri no"), column("Segment", "Segment"))),
        [],
        [],
        [],
        [],
    )
    merged = plan.tables[0]
    merged.record.update(Grain="Müşteri", KeyColumns="PartyId", BusinessDomain="CRM")
    model = FakeModel({"karar": "ayni"})
    evidence = {(KEY.casefold(), "partyid"): ["p.PartyNk AS PartyId"]}
    asyncio.run(describe_tables(plan.tables, model, evidence))
    payloads = {json.loads(r.user).get("kolon"): json.loads(r.user) for r in model.requests}
    party = payloads["PartyId"]
    assert party["nesne"]["satir_duzeyi"] == "Müşteri"
    assert party["nesne"]["is_alani"] == "CRM"
    assert party["kardes_kolonlar"] == ["Segment"]
    assert party["mevcut"] == "Müşteri no"
    assert party["kanit"] == ["p.PartyNk AS PartyId"]
    assert payloads["Segment"]["kanit"] == []


def test_a_number_from_the_code_is_accepted_and_the_summary_follows() -> None:
    plan = merge(snapshot((table(),), (column("Total", "Gönderilen sayı"),)), [], [], [], [])
    model = FakeModel(
        {
            "ColumnDescription": "Son 15 günde görülen bildirim sayısı.",
            "Summary": "Görülen bildirim · son 15 gün",
            "karar": "celisiyor",
        }
    )
    evidence = {(KEY.casefold(), "total"): ["DATEADD(DAY,-15,GETDATE())"]}
    outcome = asyncio.run(describe_tables(plan.tables, model, evidence))
    record = plan.tables[0].columns[0].record
    assert record["ColumnDescription"] == "Son 15 günde görülen bildirim sayısı."
    assert record["Summary"] == "Görülen bildirim · son 15 gün"
    assert any("çelişiyordu" in warning for warning in outcome.warnings)


def test_an_unchanged_answer_and_an_existing_row_stay_as_they_are() -> None:
    plan = merge(
        snapshot((table(),), (column("PartyId"),)),
        [prior_object(ObjectDescription="Elle", DatasetGroup="Müşteri")],
        [],
        [prior_column("PartyId", ColumnDescription="Navigator metni.")],
        [],
    )
    model = FakeModel({"ColumnDescription": "Değişti.", "karar": "eklendi"})
    asyncio.run(describe_tables(plan.tables, model))
    assert model.requests == []
    assert plan.tables[0].columns[0].record["ColumnDescription"] == "Navigator metni."


def test_an_edited_description_survives_the_next_update_and_keeps_its_original() -> None:
    plan = merge(
        snapshot((table(),), (column("PartyId", "Müşteri no"),)),
        [prior_object(DatasetGroup="Müşteri")],
        [{"origins": {"ObjectName": "kaynak"}}],
        [prior_column("PartyId", ColumnDescription="Müşteri numarası.")],
        [
            {
                "origins": {"ColumnDescription": ORIGIN_EDITED},
                "description_before": "Müşteri no",
            }
        ],
    )
    merged = plan.tables[0].columns[0]
    assert merged.record["ColumnDescription"] == "Müşteri numarası."
    assert plan.column_meta()[0]["description_before"] == "Müşteri no"


@pytest.mark.parametrize(
    "text",
    [
        "Noktasız metin",
        "Son 90 gün.",
        "Müşteri bilgisi. KVKK kapsamında kişisel veridir.",
        "Segment analizinde kullanılır.",
        "Genellikle aktif müşteri.",
        "T3 tablosundan gelir.",
        "x" * 500 + ".",
        "İki\nsatır.",
    ],
)
def test_a_model_description_breaking_the_rules_is_refused(text: str) -> None:
    assert valid_description(text, "Son 60 gün", COLUMN_TEXT_MAX) is False


def test_a_refused_rewrite_leaves_the_source_text() -> None:
    plan = merge(snapshot((table(),), (column("PartyId", "Son 60 gün"),)), [], [], [], [])
    model = FakeModel({"ColumnDescription": "Son 90 gün.", "karar": "eklendi"})
    asyncio.run(describe_tables(plan.tables, model))
    assert plan.tables[0].columns[0].record["ColumnDescription"] == "Son 60 gün"
    assert "description_before" not in plan.column_meta()[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Müşteri adı. KVKK kapsamında kişisel veri; sadece yetkili erişimlerde açık gösterilir.",
            "Müşteri adı.",
        ),
        ("Doğrulamada kullanılır; KVKK kapsamında kişisel veridir.", "Doğrulamada kullanılır."),
        ("Bordroda kullanılır; KVKK kapsamında hassas veridir.", "Bordroda kullanılır."),
        (
            "KVKK ve açık rıza kapsamında kampanya iletişiminde kullanılır.",
            "KVKK ve açık rıza kapsamında kampanya iletişiminde kullanılır.",
        ),
        ("KVKK kapsamında kişisel veridir.", "KVKK kapsamında kişisel veridir."),
    ],
)
def test_only_the_marking_sentence_leaves_a_text(text: str, expected: str) -> None:
    assert without_marking(text) == expected


def test_the_marking_leaves_existing_records_and_is_reported() -> None:
    plan = merge(
        snapshot((table(),), (column("PartyId"),)),
        [prior_object(ObjectDescription="Elle", DatasetGroup="Grup")],
        [],
        [
            prior_column(
                "PartyId",
                ColumnDescription="Ad. KVKK kapsamında kişisel veridir.",
                Summary="Ad · KVKK",
            )
        ],
        [],
    )
    record = plan.tables[0].columns[0].record
    assert record["ColumnDescription"] == "Ad."
    assert record["Summary"] == "Ad"
    assert {c.field for c in plan.changes if c.kind == "column_changed"} == {
        "ColumnDescription",
        "Summary",
    }


def test_a_left_out_database_keeps_its_records_and_is_not_removed() -> None:
    other = prior_object(Grain="Kişi")
    other.update(
        ObjectKey="ERPDM.HRM.vPerson", DatabaseName="ERPDM", SchemaName="HRM", ObjectName="vPerson"
    )
    person = prior_column("Name", Role="Ad")
    person.update(DatabaseName="ERPDM", SchemaName="HRM", ObjectName="vPerson")
    plan = merge(
        snapshot((table(),), (column("PartyId"),)),
        [prior_object(), other],
        [],
        [prior_column("PartyId"), person],
        [],
        ("ERPDM",),
    )
    assert plan.removed_tables == 0
    assert plan.removed_columns == 0
    kept = next(t for t in plan.tables if t.key == "ERPDM.HRM.vPerson")
    assert kept.record["Grain"] == "Kişi"
    assert kept.columns[0].record["Role"] == "Ad"
    assert kept.needs_model is False


def test_a_procedure_column_takes_navigators_spelling_over_a_near_miss() -> None:
    plan = merge(
        snapshot((table(),), (column("PersonnelFag", "Kaynak"),), unverified_tables=(KEY,)),
        [prior_object(ObjectDescription="Elle", DatasetGroup="Müşteri")],
        [],
        [prior_column("PersonnelFlag", ColumnDescription="Navigator metni", Role="Bayrak")],
        [],
    )
    merged = plan.tables[0].columns[0].record
    assert merged["ColumnName"] == "PersonnelFlag"
    assert merged["ColumnDescription"] == "Navigator metni"
    assert plan.removed_columns == 0
    assert "column_corrected" in kinds(plan)


def test_a_navigator_record_the_warehouse_has_stays_though_the_source_lost_it() -> None:
    other = prior_object(Grain="Eski")
    other.update(ObjectKey="EDWDM.CUS.vKept", ObjectName="vKept")
    kept_column = prior_column("Kolon", Role="Kod")
    kept_column["ObjectName"] = "vKept"
    plan = merge(
        snapshot(
            (table(),),
            (column("PartyId"),),
            catalogs={
                "EDWDM": {"CUS": {"vParty": ["PartyId", "OnlyHere"], "vKept": ["Kolon"]}},
            },
        ),
        [prior_object(), other],
        [],
        [
            prior_column("PartyId"),
            prior_column("OnlyHere", Role="Ad"),
            prior_column("Gone"),
            kept_column,
        ],
        [],
    )
    assert plan.removed_tables == 0
    assert plan.removed_columns == 1
    assert {t.key for t in plan.tables} == {KEY, "EDWDM.CUS.vKept"}
    names = [c.record["ColumnName"] for c in plan.tables[1].columns]
    assert set(names) == {"OnlyHere", "PartyId"}
    assert {"table_kept", "column_kept", "column_removed"} <= set(kinds(plan))


def test_a_procedure_keeps_a_navigator_column_the_source_lost() -> None:
    plan = merge(
        snapshot(
            (table(),),
            (column("PartyId"),),
            unverified_tables=(KEY,),
            catalogs={"EDWDM": {"CUS": {"vParty": None}}},
        ),
        [prior_object()],
        [],
        [prior_column("PartyId"), prior_column("OnlyNavigator", Role="Ad")],
        [],
    )
    assert plan.removed_columns == 0
    assert len(plan.tables[0].columns) == 2


def test_only_tables_needing_the_model_reach_it() -> None:
    tables = _new_table("PartyId")
    tables[0].needs_model = False
    model = FakeModel({"columns": []})
    asyncio.run(fill_tables(tables, model, _no_progress))
    assert model.requests == []


@pytest.mark.parametrize(
    ("name", "tokens"),
    [("CustomerKKBRisk", ["Customer", "KKB", "Risk"]), ("TRX_Amount", ["TRX", "Amount"])],
)
def test_name_tokens(name: str, tokens: list[str]) -> None:
    assert name_tokens(name) == tokens


def test_suggestions_come_only_from_candidates_and_skip_known_words() -> None:
    tables = _new_table("KKBRisk", "KKBLimit")
    assert "kkb" in {t.casefold() for t, _n in candidates(tables, set())}
    assert "kkb" not in {t.casefold() for t, _n in candidates(tables, {"kkb"})}
    model = FakeModel(
        {
            "terms": [
                {"term": "KKB", "equivalents": ["Kredi Kayıt Bürosu"], "note": ""},
                {"term": "Uydurma", "equivalents": ["x"]},
                {"term": "Risk", "equivalents": []},
            ],
            "stopwords": ["Limit", "Yok"],
        }
    )
    suggestions, answered = asyncio.run(suggest(tables, set(), model))
    assert answered is True
    assert [(s.kind, s.value) for s in suggestions] == [("term", "KKB"), ("stopword", "Limit")]
