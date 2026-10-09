"""The dictionary explorer's parity data (007-dictionary-explorer Decision 1 and Test strategy).

    python -B -m tests.parity.explorer source   # with the source copy's src on the path
    python -B -m tests.parity.explorer target

Prints, for one side, the star map (``App.galaxy``), the table search (``App.objects``) for a set
of queries made of the parity questions, the synthetic dictionary's table names, schema-qualified
names, keys, name parts and column name parts, and the detail of every table
(``App.object_detail``), all on the synthetic dictionary with the seed word lists and the default
settings. ``elapsed_ms`` is set to 0. The source's own ``App`` methods run on a stand-in that
carries only the engine and the table index they read. The source side's output is the committed
snapshot ``explorer.json``.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests.parity import dump
from tests.parity.driver import read_questions
from tests.parity.fake_model import FakeAnalyst
from tests.parity.harness import QUESTIONS, STOPWORDS, TERMS, WORKBOOK

UNKNOWN_KEY = "SYNDM.yok.Tablo"


def queries(galaxy: list[dict[str, Any]], details: dict[str, dict[str, Any]]) -> list[str]:
    """The search texts: empty and blank, the parity questions, then per table its name, the
    name in other letters, ``Şema.ad``, the key, name parts and column name parts."""

    out = ["", "   ", "ab", "limit", "doluluk oranı", "PartyId", "  kart  "]
    out += [q.query for q in read_questions(QUESTIONS)]
    for star in galaxy:
        name, key = star["name"], star["key"]
        schema = star["schema"].split(".", 1)[1]
        columns = [c["column"] for c in details[key]["columns"]]
        out += [name, name.upper(), name.lower(), f"{schema}.{name}", key, name[:3], name[:2]]
        out += [columns[0], columns[-1][:6]]
    return list(dict.fromkeys(out))


def _collect(side: Any, galaxy: Any, search: Any, detail: Any) -> dict[str, Any]:
    stars = galaxy()
    details = {star["key"]: detail(star["key"]) for star in stars}
    searches = {}
    for n, text in enumerate(queries(stars, details), 1):
        result = search(text)
        result["elapsed_ms"] = 0
        searches[f"s{n:04d}"] = {"query": text[:80], "digest": dump.digest(result)}
    return {
        "galaxy": stars,
        "details": {key: dump.digest(value) for key, value in details.items()},
        "unknown_detail": detail(UNKNOWN_KEY),
        "searches": searches,
    }


def _engine(side: Any) -> Any:
    dictionary, _parsed = side.parse_dictionary(WORKBOOK.read_bytes())
    groups, stop = side.word_lists(TERMS, STOPWORDS)
    return side.engine(dictionary, {}, groups, stop, side.client(FakeAnalyst()))


def _source(tmp: Path) -> dict[str, Any]:
    from vsa.web.server import App

    from tests.parity.run_source import SourceSide

    side = SourceSide(tmp)
    app = SimpleNamespace(engine=_engine(side))
    app.object_index = App._object_index(app)  # type: ignore[arg-type]

    def detail(key: str) -> Any:
        try:
            return App.object_detail(app, key)  # type: ignore[arg-type]
        except KeyError:
            return None

    return _collect(
        side,
        lambda: App.galaxy(app),  # type: ignore[arg-type]
        lambda text: App.objects(app, text),  # type: ignore[arg-type]
        detail,
    )


def _target() -> dict[str, Any]:
    from app.services import explorer
    from tests.parity.run_target import TargetSide

    side = TargetSide()
    engine = _engine(side)
    rows = explorer.table_index(engine)
    return _collect(
        side,
        lambda: explorer.galaxy(rows),
        lambda text: explorer.search(engine, rows, text),
        lambda key: explorer.table_detail(engine, key),
    )


def collect(side: str) -> dict[str, Any]:
    if side == "source":
        with tempfile.TemporaryDirectory(prefix="parity-explorer-") as tmp:
            return _source(Path(tmp))
    return _target()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)  # the engines log names they drop; nothing to see here
    json.dump(collect(sys.argv[1]), sys.stdout, ensure_ascii=False, sort_keys=True, indent=1)
    sys.stdout.write("\n")
