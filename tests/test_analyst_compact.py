"""Compact analyst material: table profiles in the catalog, ``Ad [Rol]: özet`` columns."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import import_workbook, write_xlsx
from vsa.dictionary_store import load_dictionary
from vsa.index.bm25 import BM25Index
from vsa.index.store import load_index, save_index
from vsa.llm.analyst import build_catalog, column_line, table_material
from vsa.loader import build_columns, object_profiles
from vsa.models import DictColumn, Dictionary, ObjectProfile


def col(i: int, obj: str, name: str, desc: str, role: str = "", summary: str = "") -> DictColumn:
    return DictColumn(
        id=i, database="EDWDM", schema="CUS", object_name=obj, column=name,
        description=desc, role=role, summary=summary,
    )  # fmt: skip


def test_catalog_uses_profile_and_falls_back_to_column_names() -> None:
    a = [col(0, "vA", "Period", "Dönem.", "Zaman", "Dönem · YYYYMM")]
    b = [col(1, "vB", "Amount", "Tutar.", "Ölçü", "Tutar · TL")]
    profiles = {
        "EDWDM.CUS.vA": ObjectProfile(
            "EDWDM.CUS.vA", "Müşteri aylık bakiyeleri.", "Müşteri × Ay", (), ("Period",), "",
            "Mevduat",
        )
    }
    cat = build_catalog({"EDWDM.CUS.vA": a, "EDWDM.CUS.vB": b}, profiles)
    assert cat.lines["EDWDM.CUS.vA"] == (
        "T1 | EDWDM.CUS.vA | Mevduat | 1 kolon | Müşteri aylık bakiyeleri. | Satır: Müşteri × Ay"
        " | Zaman: Period"
    )
    assert cat.lines["EDWDM.CUS.vB"].endswith("Kolonlar: Amount")  # no profile: names
    with_names = build_catalog({"EDWDM.CUS.vA": a}, profiles, with_columns=True)
    assert with_names.lines["EDWDM.CUS.vA"].endswith("Kolonlar: Period")


def test_column_line_compact_and_detail() -> None:
    c = col(0, "vA", "BalanceTL", "Ayın son günündeki cari hesap bakiyesi (TL).", "Ölçü",
            "Cari hesap bakiyesi · TL · ay sonu")  # fmt: skip
    compact = "- BalanceTL [Ölçü]: Cari hesap bakiyesi · TL · ay sonu"
    assert column_line(c, 400, detail=False) == compact
    assert column_line(c, 400).endswith("Ayın son günündeki cari hesap bakiyesi (TL).")
    bare = col(1, "vA", "X", "Açıklama.")
    assert column_line(bare, 400, detail=False) == "- X: Açıklama."  # no summary: description


def test_table_material_details_only_the_relevant_columns() -> None:
    cols = [
        col(0, "vA", "CustomerPartyId", "Müşteri anahtarı.", "Anahtar", "Müşteri SKEY"),
        col(1, "vA", "BalanceTL", "Uzun açıklama bakiye.", "Ölçü", "Bakiye · TL"),
        col(2, "vA", "Period", "Uzun açıklama dönem.", "Zaman", "Dönem · YYYYMM"),
    ]
    text = table_material("EDWDM.CUS.vA", "T1", cols, {1: 1.0}, 400, 90, detail_columns=1)
    assert "- BalanceTL [Ölçü]: Uzun açıklama bakiye." in text
    assert "- Period [Zaman]: Dönem · YYYYMM" in text
    full = table_material("EDWDM.CUS.vA", "T1", cols, {}, 400, 90)  # default: all detailed
    assert "- Period [Zaman]: Uzun açıklama dönem." in full


def test_loader_reads_role_summary_and_profiles(tmp_path: Path) -> None:
    rows: list[dict[str, object]] = [{
        "DatabaseName": "EDWDM", "SchemaName": "CUS", "ObjectName": "vA",
        "ColumnName": "Period", "ColumnDescription": "Dönem.",
        "Role": "Zaman", "Summary": "Dönem · YYYYMM",
    }]  # fmt: skip
    (c,), _ = build_columns(rows)
    assert (c.role, c.summary) == ("Zaman", "Dönem · YYYYMM")
    objects: list[dict[str, object]] = [{
        "ObjectKey": "EDWDM.CUS.vA", "ObjectDescription": "Aylık özet.",
        "Grain": "Müşteri × Ay",
        "KeyColumns": "CustomerPartyId, Period", "TimeColumns": "Period",
        "BusinessDomain": "Müşteri", "DatasetGroup": "Müşteri",
    }]  # fmt: skip
    prof = object_profiles(objects)["EDWDM.CUS.vA"]
    assert prof.key_columns == ("CustomerPartyId", "Period") and prof.grain == "Müşteri × Ay"

    path = write_xlsx(tmp_path / "d.xlsx", {"Objeler": objects, "Kolonlar": rows})
    d = load_dictionary(import_workbook(path, tmp_path / "d.jsonl"))
    assert d.objects["EDWDM.CUS.vA"].description == "Aylık özet."
    assert d.columns[0].dataset_group == "Müşteri"

    # the index keeps role, summary and profiles
    bm25 = BM25Index.build([{"name": ["period"]}], {"name": 1.0}, 1.2, 0.75)
    save_index(tmp_path / "idx", d, bm25, {})
    loaded, _, _ = load_index(tmp_path / "idx")
    assert loaded.columns[0].summary == "Dönem · YYYYMM"
    assert loaded.objects == d.objects


def test_old_index_without_profiles_loads(tmp_path: Path) -> None:
    d = Dictionary([col(0, "vA", "X", "Açıklama.")], "x.xlsx", "abc-1")
    bm25 = BM25Index.build([{"name": ["x"]}], {"name": 1.0}, 1.2, 0.75)
    save_index(tmp_path, d, bm25, {})
    (tmp_path / "objects.json").unlink()
    loaded, _, _ = load_index(tmp_path)
    assert loaded.objects == {} and loaded.columns[0].role == ""


def test_negation_word_is_not_a_request_concept() -> None:
    """"tüm limitler değil" must not make "değil" a concept that points at the trap."""
    from vsa.expansion.query_expander import QueryExpander

    q = QueryExpander([], [], frozenset()).expand("kart limiti, toplam limit değil")
    assert "değil" not in [c.label for c in q.content_concepts]


def test_topic_index_reads_object_profiles() -> None:
    """A table whose profile is about the request wins the table-level search (ADR-040)."""
    from vsa.features import build_features
    from vsa.scoring.topic import build_topic_index

    a = [build_features(col(0, "vA", "Amount", "Tutar."), frozenset())]
    b = [build_features(col(1, "vB", "Amount", "Tutar."), frozenset())]
    keys, index = build_topic_index(
        {"EDWDM.CUS.vA": a, "EDWDM.CUS.vB": b}, {"EDWDM.CUS.vB": ["harcama", "analitik"]}
    )
    (doc, _), *_ = index.search({"harcama": 1.0}, top_k=2)
    assert keys[doc] == "EDWDM.CUS.vB"

