"""Object-level aggregation (HANDOVER §8, ADR-005, ADR-011) and validation (§11)."""

from __future__ import annotations

from vsa.config import ObjectWeights
from vsa.expansion.query_expander import QueryExpander
from vsa.features import build_features
from vsa.models import ColumnHit, DictColumn, Level, ObjectMatch
from vsa.scoring.aggregate import ObjectColumns, aggregate
from vsa.scoring.rules import score_column
from vsa.text.normalize import load_stopwords
from vsa.validate import validate

from .test_search import GROUPS

STOP = load_stopwords(["ve", "bazında", "gösteren", "tablo"])


def build(
    tables: dict[str, list[tuple[str, str]]],
) -> tuple[list[DictColumn], dict[str, ObjectColumns]]:
    cols: list[DictColumn] = []
    for obj, fields in tables.items():
        for name, desc in fields:
            cols.append(DictColumn(len(cols), "DB", "S", obj, name, desc))
    feats = [build_features(c, STOP) for c in cols]
    objs: dict[str, list] = {}  # type: ignore[type-arg]
    for f in feats:
        objs.setdefault(f.col.object_key, []).append(f)
    return cols, {k: ObjectColumns(k, tuple(v)) for k, v in objs.items()}


def run(tables: dict[str, list[tuple[str, str]]], query: str) -> list[ObjectMatch]:
    _, objects = build(tables)
    feats = [f for o in objects.values() for f in o.features]
    q = QueryExpander(GROUPS, feats, STOP).expand(query)
    hits: dict[int, ColumnHit] = {
        f.col.id: score_column(f, 1.0, 1.0, q) for f in feats
    }
    return aggregate(hits, q, objects, ObjectWeights(), 0.25)


def test_coverage_beats_single_strong_column() -> None:
    """Ek A.1: the winner carries several concepts TOGETHER, plus a period column."""
    ranked = run(
        {
            "vWide": [
                ("CustomerPartyId", "Müşteri anahtarı."),
                ("Period", "Dönem, YYYYMM."),
                ("ConsumerBalance", "Tüketici kredisi risk bakiyesi."),
                ("HousingBalance", "Gayrimenkul risk bakiyesi."),
                ("CardBalance", "Kredi kartı risk bakiyesi."),
            ],
            "vNarrow": [
                ("CustomerPartyId", "Müşteri anahtarı."),
                ("CardRisk", "Müşterinin kredi kartı risk tutarı; kredi kartı riski."),
            ],
        },
        "Müşteri bazında aylık risk: kredi kartı, gayrimenkul, ihtiyaç kredisi",
    )
    assert ranked[0].object_name == "vWide"
    assert ranked[0].components["coverage"] > ranked[1].components["coverage"]
    assert ranked[0].components["time"] == 1.0
    assert ranked[1].components["time"] == 0.0


def test_time_component_prefers_period_for_monthly() -> None:
    ranked = run(
        {
            "vPeriod": [("Period", "Dönem."), ("RiskAmount", "Risk tutarı.")],
            "vDaily": [("DataDate", "Veri tarihi."), ("RiskAmount", "Risk tutarı.")],
        },
        "aylık risk tutarı",
    )
    by_name = {m.object_name: m for m in ranked}
    assert by_name["vPeriod"].components["time"] == 1.0
    assert by_name["vDaily"].components["time"] == 0.8


def test_granularity_only_when_customer_view_requested() -> None:
    tables = {
        "vTxn": [("TranId", "İşlem no."), ("RiskAmount", "Risk tutarı.")],
    }
    assert "granularity" not in run(tables, "risk tutarı")[0].components
    m = run(tables, "müşteri risk tutarı")[0]
    assert m.components["granularity"] == 0.5


def test_inapplicable_components_do_not_give_free_points() -> None:
    """ADR-011: no time/customer concept -> those weights are dropped, not set to 1."""
    m = run({"vX": [("Foo", "Alakasız bir alan.")]}, "gayrimenkul risk")
    if m:
        assert set(m[0].components) == {"best_column", "coverage"}


def test_related_columns_include_concept_carriers_and_time() -> None:
    ranked = run(
        {
            "vWide": [
                ("Period", "Dönem."),
                ("ConsumerBalance", "Tüketici kredisi risk bakiyesi."),
                ("HousingBalance", "Gayrimenkul bakiyesi."),
            ]
        },
        "aylık ihtiyaç kredisi ve gayrimenkul riski",
    )
    roles = {h.col.column: h.role for h in ranked[0].columns}
    assert roles["Period"] == "zaman"
    assert "HousingBalance" in roles


def test_levels_assigned() -> None:
    ranked = run({"v": [("CardLimitFullness", "Kart limit doluluk oranı.")]}, "kart limit doluluk")
    assert ranked[0].level in Level


def test_validation_drops_unknown_columns() -> None:
    cols, _ = build({"vA": [("Real", "x")]})
    real = cols[0]
    ghost = DictColumn(99, "DB", "S", "vA", "Ghost", "x")
    m = ObjectMatch(
        "DB.S.vA", "DB", "S", "vA", [], 0.9, Level.HIGH,
        [ColumnHit(real, 0.9), ColumnHit(ghost, 0.9)], {}, [], [],
    )  # fmt: skip
    kept, dropped = validate([m], {real.key})
    assert dropped == 1
    assert [h.col.column for h in kept[0].columns] == ["Real"]


def test_validation_drops_object_without_valid_columns() -> None:
    ghost = DictColumn(0, "DB", "S", "vGhost", "Ghost", "x")
    m = ObjectMatch(
        "DB.S.vGhost", "DB", "S", "vGhost", [], 0.9, Level.HIGH,
        [ColumnHit(ghost, 0.9)], {}, [], [],
    )  # fmt: skip
    kept, dropped = validate([m], set())
    assert kept == [] and dropped == 1
