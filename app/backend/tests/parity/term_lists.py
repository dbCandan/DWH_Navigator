"""The term list's parity data (005-list-search Decision 10 and Test strategy).

    python -B -m tests.parity.term_lists source   # with the source copy's src on the path
    python -B -m tests.parity.term_lists target

Prints, for one side: ``parse_term_sheet`` on row sets (terms, header and notes, or the message);
the whole reading of workbooks built here in memory (row and column limits on every sheet, other
sheets, number cells, unreadable bytes); and the list report (``write_list_report``) of lists
answered by the side's own engine with the parity fake analyst on the synthetic dictionary —
running, stopped, complete, with failed and unanswered terms, a "Analiz yapılamadı" answer and a
term starting with "=" — read back cell by cell with styles, merged cells, the filter, the frozen
pane and the term links. The source side's output is the committed snapshot ``term_lists.json``.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

from tests.parity import dump, excel_dump
from tests.parity.driver import GENERATED_AT
from tests.parity.fake_model import (
    NO_CANDIDATES,
    NO_MODEL,
    NORMAL,
    TIMEOUT,
    FakeAnalyst,
)
from tests.parity.harness import STOPWORDS, TERMS, WORKBOOK

NAN = float("nan")
ERROR = "Bu terim analiz edilirken beklenmeyen bir hata oluştu; listeyi sürdürerek yeniden deneyin."
ROW_CASES: list[list[list[Any]]] = [
    [["Terim"], [" kredi  kartı "], [None], [NAN], ["Kredi kartı"], ["mevduat"]],
    [["kredi kartı"], ["mevduat"]],
    [["Terimler:"], ["İŞLEM"], ["işlem"], ["islem"], ["ıslak"], ["ISLAK"]],
    [["  Talep. "], ["a"]],
    [["İHTİYAÇ"], ["a"]],
    [["KONU"], ["a"], [None], [None]],
    [],
    [[None], [None]],
    [["Terim", "Açıklama"], ["kart", "x"]],
    [[None, "Terim"], [None, "kart"]],
    [[None, None, "Terim"], [None, "x", "kart"]],
    [[None], ["kart"]],
    [["Terim"], [None]],
    [["Terim"], ["x" * 500], ["y" * 501]],
    [["Terim"], *([f"t{i}"] for i in range(200))],
    [["Terim"], *([f"t{i}"] for i in range(201))],
    [["Terim"], *([f"t{i % 200}"] for i in range(400))],
    [["Terim"], [5.0], [12], [3.25], [True], ["  çok   boşluklu    terim  "]],
    [["=başlık"], ["=1+1"], ["+kart"]],
]
OTHER_SHEETS = [[], ["Sayfa2"], ["Ek 1", "Ek 2"]]
# (sheets: (title, rows)); every workbook is read as a whole.
WORKBOOK_CASES: list[list[tuple[str, list[list[Any]]]]] = [
    [("Liste", [["Terim"], ["kart"], ["mevduat"]]), ("Boş", [])],
    [("Liste", [["Terim"], ["kart"]]), ("Notlar", [["not"]]), ("Diğer", [[None, "x"]])],
    [("Liste", [["Terim"], *([f"t{i % 150}"] for i in range(2000))])],
    [("Liste", [["Terim"], *([f"t{i % 150}"] for i in range(2000)), ["fazla"]])],
    [("Liste", [["Terim"], *([f"t{i % 150}"] for i in range(2000)), [None], [None]])],
    [("Liste", [["Terim"], ["kart"]]), ("Ek", [["x"]] * 2002)],
    [("Liste", [["Terim"], ["kart"]]), ("Ek", [["x"]] * 2001)],
    [("Liste", [[None] * 50 + ["Terim"], [None] * 50 + ["kart"]])],
    [("Liste", [["Terim"] + [None] * 48 + ["x"], ["kart"]])],
    [("Liste", [[None]]), ("Ek", [["Terim"], ["kart"]])],
    [("Liste", [["Terim"], [5.0], [12], ["=1+1"], ["kart"]])],
]
RAW_CASES = [b"not a workbook", b"Terim\nkart\n", b"PK\x03\x04bozuk"]
# (term, fake analyst scenario) of the answered lists.
TERMS_ASKED = [
    ("kart limit doluluk", NORMAL),
    ("Müşterinin kredi risk skoru", NORMAL),
    ("Uzay gemisi yakıt seviyesi", NORMAL),
    ("=1+1 kart limiti", NORMAL),
    ("mevduat bakiyesi", NO_CANDIDATES),
    ("kredi kartı borcu", NO_MODEL),
    ("Müşterinin sektör bazlı mevduat dağılımı", TIMEOUT),
]


def _workbook(sheets: list[tuple[str, list[list[Any]]]]) -> bytes:
    book = Workbook()
    book.remove(book.active)  # type: ignore[arg-type]
    for title, rows in sheets:
        ws = book.create_sheet(title)
        for row in rows:
            ws.append(row)
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def _outcome(read: Any, *args: Any) -> dict[str, Any]:
    try:
        r = read(*args)
    except ValueError as exc:
        return {"error": str(exc)}
    return {"terms": r.terms, "header": r.header, "notes": r.notes}


def _links(data: bytes) -> list[Any]:
    book = load_workbook(BytesIO(data))
    return [
        [ws.title, c.coordinate, c.hyperlink.target, c.hyperlink.location]
        for ws in book.worksheets
        for row in ws.iter_rows()
        for c in row
        if c.hyperlink is not None
    ]


def _lists(side: Any, models: Any) -> list[tuple[str, Any]]:
    dictionary, _ = side.parse_dictionary(WORKBOOK.read_bytes())
    groups, stop = side.word_lists(TERMS, STOPWORDS)
    core = FakeAnalyst()
    engine = side.engine(dictionary, {}, groups, stop, side.client(core))
    results = []
    for term, scenario in TERMS_ASKED:
        core.begin(term, scenario)
        result = engine.analyze(term, 5)
        result.generated_at = GENERATED_AT
        results.append(result)
    ListItem, ListResult = models

    def listed(cancelled: bool, answered: int, error_at: int | None, notes: list[str]) -> Any:
        items = []
        for n, (term, _scenario) in enumerate(TERMS_ASKED, 1):
            item = ListItem(n, term)
            if n == error_at:
                item.error, item.elapsed_ms = ERROR, 1500
            elif n <= answered:
                item.result, item.elapsed_ms = results[n - 1], 1000 * n + 234
            items.append(item)
        return ListResult(
            name="terimler.xlsx",
            items=items,
            dictionary_source="dictionary.jsonl",
            dictionary_version=dictionary.version,
            generated_at=GENERATED_AT,
            cancelled=cancelled,
            header="Terim",
            notes=notes,
        )

    notes = [
        "1 boş satır atlandı.",
        "Yalnız ilk sayfa okundu; şu sayfalardaki veriler alınmadı: Ek.",
    ]
    return [
        ("running", listed(False, 3, 2, notes)),
        ("stopped", listed(True, 4, 2, [])),
        ("complete", listed(False, 7, None, notes[:1])),
        ("complete_with_error", listed(False, 7, 5, [])),
        ("nothing_answered", listed(True, 0, None, [])),
    ]


def _collect(parse: Any, load: Any, side: Any, models: Any, report: Any) -> dict[str, Any]:
    parsed = [_outcome(parse, rows, other) for rows in ROW_CASES for other in OTHER_SHEETS]
    read = [_outcome(load, _workbook(sheets)) for sheets in WORKBOOK_CASES]
    read += [_outcome(load, raw) for raw in RAW_CASES]
    reports = {}
    for name, listed in _lists(side, models):
        data = report(listed)
        reports[name] = {"workbook": dump.digest(excel_dump.workbook(data)), "links": _links(data)}
    return {"parse": parsed, "read": read, "reports": reports}


def _source(tmp: Path) -> dict[str, Any]:
    from vsa.loader import load_term_list, parse_term_sheet
    from vsa.models import ListItem, ListResult
    from vsa.report.excel import write_list_report

    from tests.parity.run_source import SourceSide

    def load(data: bytes) -> Any:
        path = tmp / "liste.xlsx"
        path.write_bytes(data)
        return load_term_list(path)

    def report(listed: Any) -> bytes:
        return write_list_report(listed, tmp / "rapor.xlsx").read_bytes()  # type: ignore[no-any-return]

    return _collect(parse_term_sheet, load, SourceSide(tmp), (ListItem, ListResult), report)


def _target() -> dict[str, Any]:
    from app.domain.analysis import ListItem, ListResult
    from app.services.analysis.loader import load_term_list, parse_term_sheet
    from app.services.analysis.report.excel import write_list_report
    from tests.parity.run_target import TargetSide

    return _collect(
        parse_term_sheet, load_term_list, TargetSide(), (ListItem, ListResult), write_list_report
    )


def collect(side: str) -> dict[str, Any]:
    if side == "source":
        with tempfile.TemporaryDirectory(prefix="parity-lists-") as tmp:
            return _source(Path(tmp))
    return _target()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)  # the engines log names they drop; nothing to see here
    json.dump(collect(sys.argv[1]), sys.stdout, ensure_ascii=False, sort_keys=True, indent=1)
    sys.stdout.write("\n")
