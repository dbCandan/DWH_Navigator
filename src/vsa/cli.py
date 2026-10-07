"""Command line interface (HANDOVER §14.1). Does I/O.

vsa index                      build the index from the dictionary
vsa ask "…" [--top 5]          one question -> Excel report
vsa ask -i terimler.xlsx       a term list, each term through the question flow -> one report
vsa serve [--open] [--auto-index]  web UI (--auto-index: build a missing / stale index first)
vsa eval [--save]              golden-set metrics
vsa feedback                   golden-set candidates from the UI's thumbs
vsa dictionary import X.xlsx   a workbook in the template becomes the dictionary (ADR-050)
vsa dictionary export Y.xlsx [--template]  the store (or the empty template) as a workbook
"""

from __future__ import annotations

import json
import logging
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from vsa import dictionary_store
from vsa.config import Settings, load_settings
from vsa.evaluation import (
    KS,
    EvalReport,
    append_history,
    evaluate,
    load_yaml_list,
    read_history,
)
from vsa.feedback import export_candidates, load_feedback, summarize
from vsa.index.store import INDEX_FORMAT, IndexMissingError
from vsa.loader import load_term_list
from vsa.models import AnalysisResult, Level, ListItem, ListResult, Verdict
from vsa.pipeline import Engine
from vsa.report.excel import report_path, write_ask_report, write_list_report
from vsa.web.server import serve as serve_app

HISTORY_PATH = Path("eval/history.jsonl")
FEEDBACK_PATH = Path("data/feedback.jsonl")
NL = "\n"

app = typer.Typer(add_completion=False, help="Veri Sözlüğü Asistanı (VSA)")
dictionary_app = typer.Typer(help="Sözlük: Excel şablonundan içe / şablona dışa aktarma")
app.add_typer(dictionary_app, name="dictionary")
console = Console()

LEVEL_STYLE = {Level.HIGH: "green", Level.MEDIUM: "yellow", Level.LOW: "red"}
VERDICT_STYLE = {Verdict.FOUND: "green", Verdict.PARTIAL: "yellow", Verdict.NOT_FOUND: "red"}

SettingsOpt = typer.Option(
    None, "--settings", help="Ayar dosyası (varsayılan data/settings.yaml)"
)


def _setup(settings_path: Path | None, verbose: bool = False) -> Settings:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(message)s",
        handlers=[RichHandler(console=Console(stderr=True), show_path=False)],
    )
    return load_settings(settings_path)


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
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    problem = _index_problem(settings)
    if problem:
        console.print(f"[yellow]Uyarı: {problem}. `vsa index` ile yeniden kurun.[/yellow]")
    return engine


def _build_index(settings: Settings) -> None:
    if not Path(settings.dictionary.store).is_file():
        console.print(f"[yellow]Sözlük yok ({settings.dictionary.store}): boş indeks kuruluyor. "
                      "Yönetim → Sözlük ya da `vsa dictionary import` ile içe aktarın."
                      "[/yellow]")  # fmt: skip
    with console.status("Sözlük okunuyor ve indeks kuruluyor…"):
        engine = Engine.from_dictionary_file(settings)
        meta = engine.save()
    console.print(
        Panel.fit(
            f"[bold]{meta['columns']:,}[/bold] kolon · [bold]{meta['objects']}[/bold] obje\n"
            f"Sürüm: {meta['dictionary_version']}\n"
            f"Uyarı: {len(meta['warnings'])} (ayrıntı için --verbose)\n"
            f"Konum: {settings.index.dir}",
            title="İndeks hazır",
            border_style="green",
        )
    )


@app.command()
def index(
    settings_path: Path | None = SettingsOpt,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Sözlükten arama indeksini kurar."""
    _build_index(_setup(settings_path, verbose))


@dictionary_app.command("import")
def dictionary_import(
    workbook: Path = typer.Argument(..., help="Sözlük şablonundaki .xlsx (Objeler · Kolonlar)"),
    settings_path: Path | None = SettingsOpt,
) -> None:
    """Şablondaki Excel'i içe aktarır: uygulamanın sözlüğü olur, indeks yeniden kurulur."""
    settings = _setup(settings_path)
    try:
        store = dictionary_store.from_workbook(workbook)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    target = Path(settings.dictionary.store)
    dictionary_store.save(store, target)
    m = store.meta
    console.print(f"[green]Aktarıldı:[/green] {m['columns']:,} kolon · {m['objects']} tablo → "
                  f"{target} (sürüm {m['version']})")  # fmt: skip
    for w in store.warnings[:10]:
        console.print(f"[yellow]• {w}[/yellow]")
    _build_index(settings)


@dictionary_app.command("export")
def dictionary_export(
    out: Path = typer.Argument(..., help="Yazılacak .xlsx"),
    template: bool = typer.Option(False, "--template", help="Yalnız boş şablonu yaz"),
    settings_path: Path | None = SettingsOpt,
) -> None:
    """Sözlüğü (ya da boş şablonu) Excel şablonu olarak yazar."""
    settings = _setup(settings_path)
    try:
        store = None if template else dictionary_store.read(Path(settings.dictionary.store))
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[green]Yazıldı:[/green] {dictionary_store.export(store, out)}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Dinlenecek adres"),
    port: int = typer.Option(8765, "--port", "-p"),
    open_browser: bool = typer.Option(False, "--open", help="Tarayıcıda aç"),
    auto_index: bool = typer.Option(
        False, "--auto-index", help="İndeks yoksa ya da sözlük değiştiyse önce indeksi kur"
    ),
    settings_path: Path | None = SettingsOpt,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Web arayüzünü başlatır (M6)."""
    settings = _setup(settings_path, verbose)
    if auto_index and (problem := _index_problem(settings)):
        console.print(f"[yellow]{problem}: indeks kuruluyor[/yellow]")
        _build_index(settings)
    engine = _load_engine(settings)
    url = f"http://{host}:{port}"
    console.print(
        Panel.fit(
            f"[bold]{url}[/bold]\n"
            f"Model: {engine.llm.model if engine.analyst_enabled else 'bağlı değil'}\n"
            "Durdurmak için Ctrl+C",
            title="DWH Navigator",
            border_style="green",
        )
    )
    if open_browser:
        webbrowser.open(url)
    serve_app(engine, host, port, Path(settings.report.out_dir), FEEDBACK_PATH, settings_path)


def _print_result(r: AnalysisResult) -> None:
    console.print(
        Panel(r.summary, title="Sonuç", border_style=VERDICT_STYLE[r.verdict], expand=False)
    )
    if r.objects:
        table = Table(show_lines=True, header_style="bold white on #1F3864")
        table.add_column("#", justify="right")
        table.add_column("Obje")
        table.add_column("İlgili Alanlar")
        table.add_column("Gerekçe", max_width=60)
        table.add_column("Kısıt / Dikkat", max_width=50)
        table.add_column("Güven", justify="right")
        for i, m in enumerate(r.objects, 1):
            style = LEVEL_STYLE[m.level]
            table.add_row(
                str(i),
                f"[bold]{m.object_name}[/bold]\n[dim]{m.database}.{m.schema}[/dim]",
                "\n".join(h.col.column for h in m.columns),
                m.reason,
                m.caveat,
                f"[{style}]%{round(m.score * 100)}\n{m.level.value}[/{style}]",
            )
        console.print(table)
    for n in r.notes:
        if n.scope in ("Netleştirme", "Kapsam"):
            console.print(f"[cyan]• {n.scope}:[/cyan] {n.text}")
    console.print(
        f"[dim]Kavramlar: {', '.join(r.concepts)} · {r.elapsed_ms} ms · "
        f"sözlük {r.dictionary_version}[/dim]"
    )


@app.command()
def ask(
    query: str = typer.Argument("", help="İş biriminin talebi"),
    input_file: Path | None = typer.Option(
        None, "--input", "-i",
        help="Terim listesi (.xlsx): A sütunu, ilk satır başlık, altında her satırda bir terim"
    ),
    top: int = typer.Option(5, "--top", "-n", help="En fazla kaç tablo önerilsin"),
    no_excel: bool = typer.Option(False, "--no-excel", help="Excel üretme, yalnızca terminal"),
    out: Path | None = typer.Option(None, "--out", help="Rapor klasörü"),
    settings_path: Path | None = SettingsOpt,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Bir talebi ya da bir terim listesini analiz eder; Excel raporu üretir."""
    if bool(query) == bool(input_file):
        console.print("[red]Ya bir talep yazın ya da -i ile bir terim listesi verin.[/red]")
        raise typer.Exit(2)
    settings = _setup(settings_path, verbose)
    out_dir = out or Path(settings.report.out_dir)
    if input_file is not None:
        _ask_list(input_file, top, no_excel, out_dir, settings)
        return
    engine = _load_engine(settings)
    result = engine.analyze(query, top_n=top)
    _print_result(result)
    if not no_excel:
        path = write_ask_report(result, report_path(out_dir, "ask", query))
        console.print(f"[green]Rapor:[/green] {path}")


def _ask_list(path: Path, top: int, no_excel: bool, out_dir: Path, settings: Settings) -> None:
    """Every term of the list through the question flow, then one report (ADR-033)."""
    try:
        read = load_term_list(path)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    terms = read.terms
    for note in read.notes:
        console.print(f"[yellow]• {note}[/yellow]")
    engine = _load_engine(settings)
    result = ListResult(
        name=path.name,
        items=[ListItem(i, t) for i, t in enumerate(terms, 1)],
        dictionary_source=Path(engine.dictionary.source_path).name,
        dictionary_version=engine.dictionary.version,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        header=read.header,
        notes=read.notes,
    )
    table = Table(header_style="bold white on #1F3864")
    for col in ("#", "Terim", "Sonuç", "En İyi Tablo", "Güven", "Süre"):
        table.add_column(col, justify="right" if col in ("#", "Güven", "Süre") else "left")
    with Progress(
        TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(),
        TimeRemainingColumn(), console=console,
    ) as progress:  # fmt: skip
        task = progress.add_task("Terimler", total=len(terms))
        for item in result.items:
            progress.update(task, description=item.term[:40])
            t0 = time.perf_counter()
            try:
                item.result = engine.analyze(item.term, top_n=top)
            except Exception as exc:  # one broken term must not lose the others
                item.error = str(exc) or type(exc).__name__
            item.elapsed_ms = round((time.perf_counter() - t0) * 1000)
            progress.advance(task)
    for item in result.items:
        r = item.result
        best = r.objects[0] if r and r.objects else None
        verdict = f"[{VERDICT_STYLE[r.verdict]}]{r.verdict.value}[/]" if r else "[red]HATA[/red]"
        table.add_row(
            str(item.index), item.term, verdict, best.object_name if best else "-",
            f"%{round(best.score * 100)}" if best else "-", f"{item.elapsed_ms / 1000:.0f} sn",
        )  # fmt: skip
    console.print(table)
    if not no_excel:
        report = write_list_report(result, report_path(out_dir, "liste", path.stem))
        console.print(f"[green]Rapor:[/green] {report}")


def _rank_cell(rank: int | None) -> str:
    if rank is None:
        return "[red]yok[/red]"
    return f"[green]{rank}[/green]" if rank <= 3 else f"[yellow]{rank}[/yellow]"


def _print_items(report: EvalReport, group: str, title: str) -> None:
    items = report.group(group)
    if not items:
        return
    table = Table(title=title, header_style="bold white on #1F3864", title_justify="left")
    for col in ("ID", "Sıra", "Birincil", "Kolon", "İlk 3", "Tuzak"):
        table.add_column(col)
    for it in items:
        cols = f"{it.columns_found}/{it.columns_total}" if it.columns_total else "-"
        traps = f"[red]{NL.join(it.trap_violations)}[/red]" if it.trap_violations else "-"
        table.add_row(
            it.id,
            _rank_cell(it.rank),
            str(it.primary_rank or "-"),
            cols,
            NL.join(k.split(".")[-1] for k in it.top[:3]),
            traps,
        )
    console.print(table)
    recalls = "  ".join(f"recall@{k}={report.recall(k, group):.2f}" for k in KS)
    console.print(
        f"[bold]{recalls}  MRR={report.mrr(group):.3f}  "
        f"kolon={report.column_recall(group):.2f}[/bold]  (n={len(items)})"
    )
    console.print()


def _print_negatives(report: EvalReport) -> None:
    if not report.negatives:
        return
    table = Table(title="Negatif set (beklenen: BULUNAMADI)", header_style="bold white on #1F3864",
                  title_justify="left")  # fmt: skip
    for col in ("ID", "Talep", "Sonuç", "En yakın", "Skor"):
        table.add_column(col)
    for n in report.negatives:
        style = "red" if n.false_answer else "green"
        table.add_row(
            n.id, n.query, f"[{style}]{n.verdict.value}[/{style}]", n.top_object,
            f"{n.top_score:.2f}",
        )  # fmt: skip
    console.print(table)
    console.print(f"[bold]Yanlış cevap oranı={report.false_answer_rate:.2f}[/bold]")
    console.print()


@app.command("eval")
def eval_cmd(
    golden: Path = typer.Option(Path("tests/golden_set.yaml"), "--golden"),
    negatives: Path = typer.Option(Path("tests/negative_set.yaml"), "--negatives"),
    save: bool = typer.Option(False, "--save", help="Metrikleri eval/history.jsonl'e ekle"),
    label: str = typer.Option("", "--label", help="Kayıt etiketi (ör. 'coverage v2')"),
    settings_path: Path | None = SettingsOpt,
) -> None:
    """Golden set ve negatif set üzerinde değerlendirme (HANDOVER §13)."""
    settings = _setup(settings_path)
    engine = _load_engine(settings)
    gold, negs = load_yaml_list(golden), load_yaml_list(negatives)

    report = evaluate(engine, gold, negs)
    _print_items(report, "ask", "Serbest metin talepleri")
    _print_negatives(report)
    if report.trap_violations:
        console.print(f"[red]Tuzak ihlali: {report.trap_violations}[/red]")
    if save:
        entry = append_history(report, HISTORY_PATH, engine, label)
        console.print(f"[green]Kaydedildi:[/green] {HISTORY_PATH} ({entry['commit']})")
        history = read_history(HISTORY_PATH)
        if len(history) >= 2:
            _print_delta(history[-2]["metrics"], history[-1]["metrics"])


def _print_delta(before: dict[str, float], after: dict[str, float]) -> None:
    table = Table(title="Önceki kayda göre fark", header_style="bold white on #1F3864",
                  title_justify="left")  # fmt: skip
    for col in ("Metrik", "Önce", "Sonra", "Fark"):
        table.add_column(col, justify="right" if col != "Metrik" else "left")
    lower_is_better = {"trap_violations", "negative.false_answer_rate"}
    for key in after:
        if key.endswith(".n") or key not in before:
            continue
        d = after[key] - before[key]
        good = (d < 0) if key in lower_is_better else (d > 0)
        style = "green" if good else ("red" if d else "dim")
        delta = f"[{style}]{d:+.3f}[/{style}]"
        table.add_row(key, f"{before[key]:.3f}", f"{after[key]:.3f}", delta)
    console.print(table)


@app.command()
def feedback(
    export: Path = typer.Option(
        Path("eval/golden_candidates.yaml"),
        "--export",
        help="Aday golden maddelerin yazılacağı yer",
    ),
) -> None:
    """Arayüz geri bildirimlerini özetler ve golden set adaylarına dönüştürür (M7)."""
    _setup(None)
    rows = summarize(load_feedback(FEEDBACK_PATH))
    if not rows:
        console.print(f"[yellow]Henüz geri bildirim yok ({FEEDBACK_PATH}).[/yellow]")
        return
    table = Table(header_style="bold white on #1F3864")
    for col in ("Talep", "👍", "👎"):
        table.add_column(col)
    for fb in rows:
        table.add_row(
            fb.query[:70],
            NL.join(k.rsplit(".", 1)[-1] for k in fb.up) or "-",
            NL.join(k.rsplit(".", 1)[-1] for k in fb.down) or "-",
        )
    console.print(table)
    n = export_candidates(FEEDBACK_PATH, export)
    console.print(
        f"[green]{n} aday golden madde yazıldı:[/green] {export} (gözden geçirip ekleyin)"
    )


if __name__ == "__main__":  # pragma: no cover
    app()
