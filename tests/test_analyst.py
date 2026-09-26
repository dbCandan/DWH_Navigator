"""ADR-029: analyst flow — catalog, validation of everything the model writes, fallback.
Scripted model replies; no server needed."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from vsa.config import Settings
from vsa.llm.analyst import (
    MentionChecker,
    build_answer,
    build_catalog,
    column_caveats,
    table_material,
)
from vsa.models import DictColumn, Dictionary, Verdict
from vsa.pipeline import Engine, Resources
from vsa.report.excel import write_ask_report


def col(i: int, obj: str, name: str, desc: str, schema: str = "CON") -> DictColumn:
    return DictColumn(i, "EDWDM", schema, obj, name, desc, desc, dataset_group="Kart")


COLUMNS = [
    col(0, "vCreditCardList", "CardRefNumber", "Kartın tekil referans numarası."),
    col(1, "vCreditCardList", "CustomerId", "Ek kart sahibinin müşteri numarası."),
    col(2, "vCreditCardList", "MainCustomerId", "Asıl kart müşterisinin numarası."),
    col(3, "vCreditCardList", "CardStatusCodeName", "Kartın güncel statüsü."),
    col(4, "vChurnInput", "NumberOfCreditCards", "Müşterinin kredi kartı sayısı.", "AIS"),
    col(5, "vChurnInput", "CustomerId", "Müşteri numarası.", "AIS"),
]
LIST = "EDWDM.CON.vCreditCardList"
CHURN = "EDWDM.AIS.vChurnInput"


def objects() -> dict[str, list[DictColumn]]:
    out: dict[str, list[DictColumn]] = {}
    for c in COLUMNS:
        out.setdefault(c.object_key, []).append(c)
    return out


class ScriptedClient:
    """Answers the two analyst steps in order; None simulates a failed call."""

    available = True
    model = "fake-analyst"

    def __init__(self, *replies: dict[str, Any] | None) -> None:
        self.replies = list(replies)
        self.systems: list[str] = []
        self.users: list[str] = []

    def chat_json(
        self, system: str, user: str, schema: Mapping[str, Any], *, max_tokens: int = 1024
    ) -> dict[str, Any] | None:
        self.systems.append(system)
        self.users.append(user)
        return self.replies.pop(0) if self.replies else None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("dense arm is off in these tests")


def engine(client: ScriptedClient) -> Engine:
    dictionary = Dictionary(COLUMNS, "sozluk.xlsx", "abc-6")
    return Engine(dictionary, Settings(), Resources(), llm=client)


SHORTLIST = {
    "interpretation": "Kart bazında künye bilgisi isteniyor.",
    "candidates": [{"id": "T2", "why": "kart listesi"}, {"id": "T99", "why": "uydurma"}],
    "confusables": [{"id": "T1", "why": "model girdisi"}],
    "search_terms": ["CreditCard", "kart"],
}


def analyst_reply(**overrides: Any) -> dict[str, Any]:
    reply: dict[str, Any] = {
        "verdict": "VAR",
        "summary": "VAR. Ana kaynak EDWDM.CON.vCreditCardList.",
        "recommendations": [
            {
                "id": "T2",
                "covers": "Kart künyesi",
                "columns": ["cardrefnumber", "MainCustomerId", "CardColour"],
                "reason": "T2 tablosu kart başına bir satır tutar. Asıl müşteri MainCustomerId.",
                "caveat": "CustomerId ek kart sahibidir.",
                "usage": "Kart künyesi isteniyorsa ilk tercih.",
                "confidence": 0.9,
            }
        ],
        "design": ["Tek tablo yeterli: T2 (vCreditCardList)."],
        "attention": ["vCreditCardList.CustomerId ek kart sahibini gösterir."],
        "notes": [
            {"scope": "Uyarı", "title": "Model girdisi", "text": "vChurnInput kart listesi değil."},
            {"scope": "Top 5 dışı", "title": "Uydurma", "text": "EDWDM.CON.vCardMagic bak."},
        ],
    }
    reply.update(overrides)
    return reply


class TestCatalog:
    def test_every_table_with_all_columns(self) -> None:
        cat = build_catalog(objects())
        assert cat.ids == {"T1": CHURN, "T2": LIST}
        assert cat.keys[LIST] == "T2"
        line = cat.text.splitlines()[1]
        assert line.startswith("T2 | EDWDM.CON.vCreditCardList | Kart | 4 kolon |")
        assert "MainCustomerId" in line and "CardStatusCodeName" in line

    def test_wide_table_keeps_keys_and_relevant_descriptions(self) -> None:
        cols = objects()[LIST]
        text = table_material(LIST, "T2", cols, {3: 1.0}, 200, full_limit=2)
        assert "- CardRefNumber: Kartın tekil" in text  # structural key on a tie
        assert "- CardStatusCodeName: Kartın güncel" in text  # most relevant first
        assert "Diğer 2 kolon (yalnız ad): CustomerId, MainCustomerId" in text


class TestMentions:
    checker = MentionChecker.build(COLUMNS)

    def test_known_names_pass(self) -> None:
        text = f"{LIST} ve {LIST}.CardRefNumber ile vCreditCardList.MainCustomerId; vPRC* hariç."
        assert self.checker.unknown(text) == []

    def test_unknown_names_found(self) -> None:
        assert self.checker.unknown("EDWDM.CON.vCardMagic") == ["EDWDM.CON.vCardMagic"]
        assert self.checker.unknown(f"{LIST}.Colour") == [f"{LIST}.Colour"]
        assert self.checker.unknown("vCreditCardList.Colour") == ["vCreditCardList.Colour"]
        assert self.checker.unknown("vCardMagic tablosu") == ["vCardMagic"]

    def test_clean_removes_only_the_bad_sentence(self) -> None:
        text, dropped = self.checker.clean("İlk cümle doğru. vCardMagic uydurma. Son cümle.")
        assert (text, dropped) == ("İlk cümle doğru. Son cümle.", 1)


class TestBuildAnswer:
    def build(self, reply: dict[str, Any], min_conf: float = 0.5) -> Any:
        cat = build_catalog(objects())
        return build_answer(
            reply, {"T2": LIST}, objects(), MentionChecker.build(COLUMNS), 5, min_conf, cat.ids
        )

    def test_validated_recommendation(self) -> None:
        a = self.build(analyst_reply())
        (rec,) = a.recommendations
        assert rec.object_key == LIST
        # case-insensitive match kept, unknown column dropped
        assert [c.column for c in rec.columns] == ["CardRefNumber", "MainCustomerId"]
        assert rec.reason.startswith("vCreditCardList tablosu")  # catalog id written as name
        assert a.design == ["Tek tablo yeterli: vCreditCardList."]  # no "vX (vX)" echo
        assert a.verdict is Verdict.FOUND
        assert [n.title for n in a.notes] == ["Model girdisi"]  # made-up table's note removed
        assert a.dropped == 2  # CardColour + the sentence naming vCardMagic

    def test_names_in_place_of_ids(self) -> None:
        recs = analyst_reply()["recommendations"]
        for written in (LIST, "vCreditCardList", "`T2`"):
            a = self.build(analyst_reply(recommendations=[{**recs[0], "id": written}]))
            assert [r.object_key for r in a.recommendations] == [LIST], written

    def test_ids_outside_the_shortlist_are_refused(self) -> None:
        recs = analyst_reply()["recommendations"]
        a = self.build(analyst_reply(recommendations=[{**recs[0], "id": "T1"}]))
        assert a.recommendations == [] and a.verdict is Verdict.NOT_FOUND
        assert a.summary.startswith("BULUNAMADI.")

    def test_low_confidence_is_not_shown(self) -> None:
        recs = analyst_reply()["recommendations"]
        a = self.build(analyst_reply(recommendations=[{**recs[0], "confidence": 0.4}]))
        assert a.recommendations == []

    def test_summary_prefix_follows_verdict(self) -> None:
        a = self.build(analyst_reply(verdict="KISMEN VAR", summary="VAR — birleştirme gerekir."))
        assert a.summary == "KISMEN VAR. birleştirme gerekir."


def test_column_caveats_pick_sentences_naming_the_column() -> None:
    texts = [
        "CustomerId ek kart sahibidir. MainCustomerId asıl müşteridir.",
        "vCreditCardList.CustomerId ile birleştirme yapılmamalı.",
    ]
    assert column_caveats("CustomerId", texts) == [
        "CustomerId ek kart sahibidir.",
        "vCreditCardList.CustomerId ile birleştirme yapılmamalı.",
    ]
    assert column_caveats("MainCustomerId", texts) == ["MainCustomerId asıl müşteridir."]
    assert column_caveats("CardRefNumber", texts) == []
    # "ör." does not end the sentence
    sentence = "Oran türetilir (ör. vCreditCardLimit) CardLimit ile."
    assert column_caveats("CardLimit", [sentence]) == [sentence]


class TestEngine:
    def test_analyst_answer(self, tmp_path: Path) -> None:
        client = ScriptedClient(SHORTLIST, analyst_reply())
        r = engine(client).analyze("müşterinin kredi kartı bilgisi")
        assert r.analyst and r.verdict is Verdict.FOUND
        assert [m.object_key for m in r.objects] == [LIST]
        m = r.objects[0]
        assert m.covers == "Kart künyesi" and m.score == 0.9 and m.llm_confidence == 0.9
        assert {h.role for h in m.columns} == {"yapısal"}
        by_name = {h.col.column: h.caveats for h in m.columns}
        # warnings name CustomerId, not the two recommended columns
        assert by_name == {"CardRefNumber": [], "MainCustomerId": []}
        assert r.design and r.attention
        assert r.notes[-1].title == "Doğrulama"
        assert r.llm_unknown_ids == 1  # T99 in the shortlist
        # step 1 sees the catalog in the system message, step 2 the full columns
        assert "T2 | EDWDM.CON.vCreditCardList" in client.systems[0]
        assert "- MainCustomerId: Asıl kart müşterisinin numarası." in client.users[1]
        assert "vChurnInput" in client.users[1]  # look-alike table as evidence

        path = write_ask_report(r, tmp_path / "r.xlsx")
        wb = load_workbook(path)
        assert wb.sheetnames == ["Özet", "Öneriler", "Alan Detayları", "Notlar ve Öneriler"]
        cells = [str(c.value) for row in wb["Özet"].iter_rows() for c in row if c.value]
        assert "Önerilen Kurgu" in cells and "Dikkat Edilmesi Gerekenler" in cells
        assert "Kart künyesi" in cells

    def test_nothing_found(self) -> None:
        empty = {**SHORTLIST, "candidates": [], "confusables": []}
        r = engine(ScriptedClient(empty)).analyze("uzay gemisi yakıtı")
        assert r.analyst and r.verdict is Verdict.NOT_FOUND and r.objects == []

    def test_model_failure_falls_back_to_rules(self) -> None:
        r = engine(ScriptedClient(None)).analyze("kredi kartı")
        assert not r.analyst  # ADR-008: rule pipeline answered

    def test_second_step_failure_falls_back(self) -> None:
        r = engine(ScriptedClient(SHORTLIST, None)).analyze("kredi kartı")
        assert not r.analyst

    def test_switched_off(self) -> None:
        client = ScriptedClient(SHORTLIST, analyst_reply())
        e = engine(client)
        e.settings.analyst.enabled = False
        assert not e.analyze("kredi kartı").analyst
