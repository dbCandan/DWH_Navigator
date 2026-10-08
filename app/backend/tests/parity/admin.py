"""The admin screen's parity data: settings schema and word lists (009 and 002 Test strategy).

    python -B -m tests.parity.admin source   # with the source copy's src on the path
    python -B -m tests.parity.admin target

Prints, for one side, the settings schema and the measured defaults, the word list checks
(``check_terms`` / ``check_stopwords``: result or message) for fixed cases, the word list
workbook read back from fixed workbooks and written from the seed lists, and the engine's reading
of the seed lists. Workbooks are built here, in memory, with the same openpyxl series on both
sides. The source side's output is the committed snapshot ``admin.json``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[4]
SEED = ROOT / "schema" / "alembic" / "seed" / "vocabulary"

TERM_CASES: list[Any] = [
    "değil",
    [1, 2],
    [],
    [{"term": " a ", "equivalents": ["b", "b", " ", "c"], "domain": " d ", "note": "n"}],
    [{"term": "", "equivalents": ["b"]}],
    [{"term": "a", "equivalents": ["b"]}, {"term": "  ", "equivalents": ["c"]}],
    [{"term": "x"}],
    [{"term": "x", "equivalents": []}],
    [{"term": "x", "equivalents": ["", " "]}],
    [
        {"term": "İŞLEM", "equivalents": ["a"]},
        {"term": "y", "equivalents": ["b"]},
        {"term": "islem", "equivalents": ["c"]},
    ],
    [{"term": "Işık", "equivalents": ["a"]}, {"term": "ışık", "equivalents": ["b"]}],
    [{"term": "kâr", "equivalents": ["a"]}, {"term": "kar", "equivalents": ["b"]}],
    [{"term": "a", "equivalents": ["b"]}] * 5001,
]
STOPWORD_CASES: list[Any] = [
    "değil",
    [{"word": "Ve"}, {"word": "ve"}, {"word": " "}, {"word": "mı", "group": "Soru"}],
    [{"word": "iki kelime"}],
    [{"word": "mi", "group": "A"}, {"word": "mı", "group": "B"}, {"word": "MU"}, {"word": "mü"}],
    [{"word": " ile ", "group": " Genel "}],
    [{"word": "x"}] * 5001,
]
# A group whose texts start with "=": they must stay texts in the workbook.
FORMULA_TERM = {"term": "=x", "equivalents": ["=y", "z"], "domain": "", "note": "=1+1"}
# (list kind, sheet title, rows) of the workbooks read back as word lists.
WORKBOOK_CASES: list[tuple[str, str, list[list[Any]]]] = [
    (
        "terms",
        "Terimler",
        [
            ["Terim", "Eşdeğerler", "Alan", "Not"],
            ["zırhlı araç", "panzer; tank, =zırh|kale\nkule", "test", None],
            [None, None, None, None],
            [5.0, 12, None, "not"],
        ],
    ),
    ("terms", "Başka", [[" TERİM ", "Eş Değerler", "açıklama"], ["a", "b", "c"]]),
    ("terms", "Terimler", [["Alan"], ["x"]]),
    ("terms", "Terimler", [["Terim", "Eşdeğerler"], [None, None]]),
    ("stopwords", "DurakKelimeler", [["Kelime", "Grup"], ["ve", "Genel"], ["iki kelime", None]]),
    ("stopwords", "DurakKelimeler", [["Grup"], ["g"]]),
    ("stopwords", "DurakKelimeler", [["Kelime"], *[[f"k{i}"] for i in range(5001)]]),
    ("stopwords", "DurakKelimeler", [["Kelime"], *[[f"k{i}"] for i in range(5000)]]),
]


def _workbook(title: str, rows: Sequence[Sequence[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = title
    for row in rows:
        sheet.append(list(row))
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _seed(name: str) -> list[dict[str, Any]]:
    lines = (SEED / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _outcome(check: Callable[[Any], Any], value: Any) -> dict[str, Any]:
    try:
        result = check(value)
    except ValueError as exc:
        return {"error": str(getattr(exc, "message", exc))}
    return {
        "result": result if not isinstance(result, list) or len(result) <= 1000 else len(result)
    }


def _sheet_dump(data: bytes) -> dict[str, Any]:
    book = load_workbook(BytesIO(data))
    sheet = book.worksheets[0]
    return {
        "title": sheet.title,
        "rows": [[c.value for c in row] for row in sheet.iter_rows()],
        "types": sorted({c.data_type for row in sheet.iter_rows() for c in row}),
        "bold": [bool(c.font.bold) for c in sheet[1]],
        "widths": {k: v.width for k, v in sorted(sheet.column_dimensions.items())},
        "freeze": sheet.freeze_panes,
    }


def _source() -> dict[str, Any]:
    from vsa import loader
    from vsa.web import settings_schema

    def read(kind: str, data: bytes) -> list[dict[str, Any]]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "liste.xlsx"
            path.write_bytes(data)
            return loader.words_from_workbook(kind, path)  # type: ignore[no-any-return]

    def write(kind: str, items: list[dict[str, Any]]) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            return loader.words_to_workbook(kind, items, Path(tmp) / "x.xlsx").read_bytes()

    def groups(rows: list[dict[str, Any]]) -> list[Any]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "terms.jsonl"
            path.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8"
            )
            return [asdict(g) for g in loader.load_term_dictionary(path)]

    def forms(rows: list[dict[str, Any]]) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stopwords.jsonl"
            path.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8"
            )
            return sorted(loader.load_stopword_file(path))

    return _collect(
        sections=settings_schema.SECTIONS,
        defaults={k: v for k, v in settings_schema.defaults().items()},
        check_terms=loader.check_terms,
        check_stopwords=loader.check_stopwords,
        read=read,
        write=write,
        groups=groups,
        forms=forms,
    )


def _target() -> dict[str, Any]:
    from app.domain.vocabulary import VocabularyList, check_stopwords, check_terms
    from app.services.search_settings_schema import defaults, section_dicts
    from app.services.vocabulary_reading import stopword_forms, term_groups
    from app.services.vocabulary_workbook import items_from_workbook, items_to_workbook

    def sections() -> list[dict[str, Any]]:
        out = section_dicts()
        for section in out:
            for field in section["fields"]:
                field["effect"] = str(field["effect"])
        return out

    return _collect(
        sections=sections(),
        defaults=defaults(),
        check_terms=check_terms,
        check_stopwords=check_stopwords,
        read=lambda kind, data: items_from_workbook(VocabularyList(kind), data),
        write=lambda kind, items: items_to_workbook(VocabularyList(kind), items),
        groups=lambda rows: [asdict(g) for g in term_groups(rows)],
        forms=lambda rows: sorted(stopword_forms(rows)),
    )


def _collect(
    *,
    sections: Any,
    defaults: Mapping[str, Any],
    check_terms: Callable[[Any], Any],
    check_stopwords: Callable[[Any], Any],
    read: Callable[[str, bytes], Any],
    write: Callable[[str, list[dict[str, Any]]], bytes],
    groups: Callable[[list[dict[str, Any]]], Any],
    forms: Callable[[list[dict[str, Any]]], Any],
) -> dict[str, Any]:
    terms, stopwords = _seed("terms.jsonl"), _seed("stopwords.jsonl")
    return {
        "settings": {
            "sections": json.loads(json.dumps(sections, ensure_ascii=False)),
            "defaults": dict(defaults),
        },
        "checks": {
            "terms": [_outcome(check_terms, case) for case in TERM_CASES],
            "stopwords": [_outcome(check_stopwords, case) for case in STOPWORD_CASES],
            "seed_terms": _outcome(check_terms, terms),
            "seed_stopwords": _outcome(check_stopwords, stopwords),
        },
        "workbooks": {
            "read": [
                _outcome(lambda data, k=kind: read(k, data), _workbook(title, rows))
                for kind, title, rows in WORKBOOK_CASES
            ],
            "write": {
                "terms": _sheet_dump(write("terms", check_terms(terms))),
                "stopwords": _sheet_dump(write("stopwords", check_stopwords(stopwords))),
                "formula": _sheet_dump(write("terms", [FORMULA_TERM])),
            },
        },
        "engine_reading": {"term_groups": groups(terms), "stopword_forms": forms(stopwords)},
    }


def collect(side: str) -> dict[str, Any]:
    return _source() if side == "source" else _target()


if __name__ == "__main__":
    json.dump(collect(sys.argv[1]), sys.stdout, ensure_ascii=False, sort_keys=True, indent=1)
    sys.stdout.write("\n")
