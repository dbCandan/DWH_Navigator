"""Command line interface. Does I/O; standard library only.

vsa index                      build the index from the dictionary
vsa ask "…" [--top 5]          one question -> Excel report
vsa ask -i terimler.xlsx       a term list, each term through the question flow -> one report
vsa serve [--open]             web UI (builds a missing / stale index first)
vsa eval [--save]              golden-set metrics
vsa dictionary import X.xlsx   a workbook in the template becomes the dictionary (ADR-050)
vsa dictionary export Y.xlsx [--template]  the store (or the empty template) as a workbook
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
import webbrowser
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from vsa import dictionary_store
from vsa.config import Settings, load_settings
from vsa.evaluation import KS, EvalReport, append_history, evaluate, load_yaml_list, read_history
from vsa.index.store import INDEX_FORMAT, IndexMissingError
from vsa.loader import load_term_list
from vsa.models import AnalysisResult, ListItem, ListResult
from vsa.pipeline import Engine
from vsa.report.excel import report_path, write_ask_report, write_list_report
from vsa.web.server import serve as serve_app

HISTORY_PATH = Path("eval/history.jsonl")
FEEDBACK_PATH = Path("data/feedback.jsonl")
# The image ships the term dictionary and stopwords here; data/ is a volume (ADR-052).
BUNDLED_LISTS = Path(__file__).parent / "defaults"


class CliError(Exception):
    """A message for the user; the command exits with status 2."""


def _say(text: str = "") -> None:
    print(text, flush=True)


def _setup(settings_path: Path | None, verbose: bool = False) -> Settings:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    settings = load_settings(settings_path)
    _seed_word_lists(settings)
    return settings


def _seed_word_lists(settings: Settings) -> None:
    """A missing term dictionary / stopword file starts as the shipped one; an existing
    file (edited on the admin screen) is never touched."""
    for target in (settings.expansion.term_dictionary, settings.expansion.stopwords):
        path, bundled = Path(target), BUNDLED_LISTS / Path(target).name
        if not path.exists() and bundled.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundled, path)
            _say(f"İlk çalıştırma: varsayılan {path} yazıldı.")


def _index_problem(settings: Settings) -> str:
    """Why the index does not fit the dictionary file; "" when it does."""
    meta_path = Path(settings.index.dir) / "meta.json"
    if not meta_path.is_file():
        return "indeks yok"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "indeks okunamadı"
    if meta.get("format") != INDEX_FORMAT:
        return "indeks formatı eski"
    store = Path(settings.dictionary.store)
    current = dictionary_store.load_dictionary(store).version if store.is_file() else ""
    if str(meta.get("dictionary_version", "")) != current:
        return "sözlük indeks kurulduktan sonra değişmiş"
    return ""


def _load_engine(settings: Settings) -> Engine:
    try:
        engine = Engine.from_index(settings)
    except IndexMissingError as exc:
        raise CliError(str(exc)) from exc
    if problem := _index_problem(settings):
        _say(f"Uyarı: {problem}. `vsa index` ile yeniden kurun.")
    return engine


def _build_index(settings: Settings) -> None:
    if not Path(settings.dictionary.store).is_file():
        _say(f"Sözlük yok ({settings.dictionary.store}): boş indeks kuruluyor. "
             "Yönetim → Sözlük ya da `vsa dictionary import` ile içe aktarın.")  # fmt: skip
    _say("Sözlük okunuyor ve indeks kuruluyor…")
    meta = Engine.from_dictionary_file(settings).save()
    _say(f"İndeks hazır: {meta['columns']:,} kolon · {meta['objects']} obje · "
         f"sürüm {meta['dictionary_version']} · {len(meta['warnings'])} uyarı · "
         f"{settings.index.dir}")  # fmt: skip


# ---------------------------------------------------------------------------- commands


def cmd_index(a: argparse.Namespace) -> None:
    _build_index(_setup(a.settings, a.verbose))


def cmd_dictionary_import(a: argparse.Namespace) -> None:
    settings = _setup(a.settings)
    try:
        store = dictionary_store.from_workbook(a.workbook)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    target = Path(settings.dictionary.store)
    dictionary_store.save(store, target)
    m = store.meta
    _say(f"Aktarıldı: {m['columns']:,} kolon · {m['objects']} tablo → {target} "
         f"(sürüm {m['version']})")  # fmt: skip
    for w in store.warnings[:10]:
        _say(f"• {w}")
    _build_index(settings)


def cmd_dictionary_export(a: argparse.Namespace) -> None:
    settings = _setup(a.settings)
    try:
        store = None if a.template else dictionary_store.read(Path(settings.dictionary.store))
    except (FileNotFoundError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    _say(f"Yazıldı: {dictionary_store.export(store, a.out)}")


def cmd_serve(a: argparse.Namespace) -> None:
    settings = _setup(a.settings, a.verbose)
    if problem := _index_problem(settings):
        _say(f"{problem}: indeks kuruluyor")
        _build_index(settings)
    engine = _load_engine(settings)
    url = f"http://{a.host}:{a.port}"
    model = engine.llm.model if engine.analyst_enabled else "bağlı değil"
    _say(f"DWH Navigator: {url} · model: {model} · durdurmak için Ctrl+C")
    if a.open:
        webbrowser.open(url)
    serve_app(engine, a.host, a.port, Path(settings.report.out_dir), FEEDBACK_PATH, a.settings)


def _print_result(r: AnalysisResult) -> None:
    _say(f"Sonuç: {r.summary}")
    for i, m in enumerate(r.objects, 1):
        _say(f"{i}. {m.database}.{m.schema}.{m.object_name} · %{round(m.score * 100)} "
             f"{m.level.value}")  # fmt: skip
        _say(f"   Alanlar: {', '.join(h.col.column for h in m.columns)}")
        if m.reason:
            _say(f"   Gerekçe: {m.reason}")
        if m.caveat:
            _say(f"   Dikkat: {m.caveat}")
    for n in r.notes:
        if n.scope in ("Netleştirme", "Kapsam"):
            _say(f"• {n.scope}: {n.text}")
    _say(f"Kavramlar: {', '.join(r.concepts)} · {r.elapsed_ms} ms · "
         f"sözlük {r.dictionary_version}")  # fmt: skip


def cmd_ask(a: argparse.Namespace) -> None:
    if bool(a.query) == bool(a.input):
        raise CliError("Ya bir talep yazın ya da -i ile bir terim listesi verin.")
    settings = _setup(a.settings, a.verbose)
    out_dir = a.out or Path(settings.report.out_dir)
    if a.input is not None:
        _ask_list(a.input, a.top, a.no_excel, out_dir, settings)
        return
    engine = _load_engine(settings)
    result = engine.analyze(a.query, top_n=a.top)
    _print_result(result)
    if not a.no_excel:
        _say(f"Rapor: {write_ask_report(result, report_path(out_dir, 'ask', a.query))}")


def _ask_list(path: Path, top: int, no_excel: bool, out_dir: Path, settings: Settings) -> None:
    """Every term of the list through the question flow, then one report (ADR-033)."""
    try:
        read = load_term_list(path)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    for note in read.notes:
        _say(f"• {note}")
    engine = _load_engine(settings)
    result = ListResult(
        name=path.name,
        items=[ListItem(i, t) for i, t in enumerate(read.terms, 1)],
        dictionary_source=Path(engine.dictionary.source_path).name,
        dictionary_version=engine.dictionary.version,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        header=read.header,
        notes=read.notes,
    )
    total = len(result.items)
    for item in result.items:
        t0 = time.perf_counter()
        try:
            item.result = engine.analyze(item.term, top_n=top)
        except Exception as exc:  # one broken term must not lose the others
            item.error = str(exc) or type(exc).__name__
        item.elapsed_ms = round((time.perf_counter() - t0) * 1000)
        r = item.result
        best = r.objects[0] if r and r.objects else None
        found = f"{best.object_name} %{round(best.score * 100)}" if best else "-"
        _say(f"[{item.index}/{total}] {item.term} · {r.verdict.value if r else 'HATA'} · "
             f"{found} · {item.elapsed_ms / 1000:.0f} sn")  # fmt: skip
    if not no_excel:
        _say(f"Rapor: {write_list_report(result, report_path(out_dir, 'liste', path.stem))}")


def _print_items(report: EvalReport, group: str, title: str) -> None:
    items = report.group(group)
    if not items:
        return
    _say(title)
    for it in items:
        cols = f"{it.columns_found}/{it.columns_total}" if it.columns_total else "-"
        top3 = ", ".join(k.split(".")[-1] for k in it.top[:3])
        traps = f" · TUZAK: {', '.join(it.trap_violations)}" if it.trap_violations else ""
        _say(f"  {it.id}: sıra {it.rank or 'yok'} · birincil {it.primary_rank or '-'} · "
             f"kolon {cols} · ilk 3: {top3}{traps}")  # fmt: skip
    recalls = "  ".join(f"recall@{k}={report.recall(k, group):.2f}" for k in KS)
    _say(f"{recalls}  MRR={report.mrr(group):.3f}  kolon={report.column_recall(group):.2f}  "
         f"(n={len(items)})\n")  # fmt: skip


def _print_negatives(report: EvalReport) -> None:
    if not report.negatives:
        return
    _say("Negatif set (beklenen: BULUNAMADI)")
    for n in report.negatives:
        mark = "YANLIŞ" if n.false_answer else "doğru"
        _say(f"  {n.id}: {n.verdict.value} ({mark}) · en yakın {n.top_object} "
             f"{n.top_score:.2f} · {n.query}")  # fmt: skip
    _say(f"Yanlış cevap oranı={report.false_answer_rate:.2f}\n")


def cmd_eval(a: argparse.Namespace) -> None:
    settings = _setup(a.settings)
    engine = _load_engine(settings)
    report = evaluate(engine, load_yaml_list(a.golden), load_yaml_list(a.negatives))
    _print_items(report, "ask", "Serbest metin talepleri")
    _print_negatives(report)
    if report.trap_violations:
        _say(f"Tuzak ihlali: {report.trap_violations}")
    if a.save:
        entry = append_history(report, HISTORY_PATH, engine, a.label)
        _say(f"Kaydedildi: {HISTORY_PATH} ({entry['commit']})")
        history = read_history(HISTORY_PATH)
        if len(history) >= 2:
            _print_delta(history[-2]["metrics"], history[-1]["metrics"])


def _print_delta(before: dict[str, float], after: dict[str, float]) -> None:
    _say("Önceki kayda göre fark")
    for key in after:
        if key.endswith(".n") or key not in before:
            continue
        _say(f"  {key}: {before[key]:.3f} → {after[key]:.3f} ({after[key] - before[key]:+.3f})")


# ---------------------------------------------------------------------------- parser


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--settings", type=Path, default=None,
                        help="Ayar dosyası (varsayılan data/settings.yaml)")  # fmt: skip
    common.add_argument("--verbose", "-v", action="store_true")

    p = argparse.ArgumentParser(prog="vsa", description="Veri Sözlüğü Asistanı (VSA)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("index", parents=[common], help="Sözlükten arama indeksini kurar")
    s.set_defaults(run=cmd_index)

    s = sub.add_parser("serve", parents=[common], help="Web arayüzünü başlatır")
    s.add_argument("--host", default="127.0.0.1", help="Dinlenecek adres")
    s.add_argument("--port", "-p", type=int, default=8765)
    s.add_argument("--open", action="store_true", help="Tarayıcıda aç")
    s.set_defaults(run=cmd_serve)

    s = sub.add_parser("ask", parents=[common], help="Bir talebi ya da terim listesini analiz eder")
    s.add_argument("query", nargs="?", default="", help="İş biriminin talebi")
    s.add_argument("--input", "-i", type=Path, default=None,
                   help="Terim listesi (.xlsx): A sütunu, ilk satır başlık")  # fmt: skip
    s.add_argument("--top", "-n", type=int, default=5, help="En fazla kaç tablo önerilsin")
    s.add_argument("--no-excel", action="store_true", help="Excel üretme, yalnızca terminal")
    s.add_argument("--out", type=Path, default=None, help="Rapor klasörü")
    s.set_defaults(run=cmd_ask)

    s = sub.add_parser("eval", parents=[common], help="Golden set ve negatif set ölçümü")
    s.add_argument("--golden", type=Path, default=Path("tests/golden_set.yaml"))
    s.add_argument("--negatives", type=Path, default=Path("tests/negative_set.yaml"))
    s.add_argument("--save", action="store_true", help="Metrikleri eval/history.jsonl'e ekle")
    s.add_argument("--label", default="", help="Kayıt etiketi")
    s.set_defaults(run=cmd_eval)

    d = sub.add_parser("dictionary", help="Sözlük: Excel şablonundan içe / şablona dışa aktarma")
    dsub = d.add_subparsers(dest="action", required=True)
    s = dsub.add_parser("import", parents=[common], help="Şablondaki Excel sözlük olur")
    s.add_argument("workbook", type=Path, help="Sözlük şablonundaki .xlsx (Objeler · Kolonlar)")
    s.set_defaults(run=cmd_dictionary_import)
    s = dsub.add_parser("export", parents=[common], help="Sözlüğü Excel şablonu olarak yazar")
    s.add_argument("out", type=Path, help="Yazılacak .xlsx")
    s.add_argument("--template", action="store_true", help="Yalnız boş şablonu yaz")
    s.set_defaults(run=cmd_dictionary_export)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        args.run(args)
    except CliError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
