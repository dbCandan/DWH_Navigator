"""Command line interface (HANDOVER §14.1). Does I/O.

vsa index                      build the index from the dictionary
vsa ask "…" [--top 5] [--no-excel] [--out out/]
vsa eval                       golden-set metrics
"""

from __future__ import annotations

import logging
import sys
import webbrowser
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

from vsa.batch import BatchAnalyzer
from vsa.config import Settings, load_settings
from vsa.evaluation import (
    KS,
    EvalReport,
    append_history,
    compare_configs,
    evaluate,
    load_yaml_list,
    read_history,
)
from vsa.index.dense import build_dense_index
from vsa.index.store import IndexMissingError
from vsa.llm.client import LLMError, OpenAICompatibleClient
from vsa.loader import file_version, load_request_file
from vsa.models import AnalysisResult, BatchResult, FieldStatus, Level, Verdict
from vsa.pipeline import Engine
from vsa.report.excel import report_path, write_ask_report, write_batch_report
from vsa.web.server import serve as serve_app

HISTORY_PATH = Path("eval/history.jsonl")
FEEDBACK_PATH = Path("data/feedback.jsonl")
NL = "\n"

app = typer.Typer(add_completion=False, help="Veri Sözlüğü Asistanı (VSA)")
console = Console()

LEVEL_STYLE = {Level.HIGH: "green", Level.MEDIUM: "yellow", Level.LOW: "red"}
STATUS_STYLE = {
    FieldStatus.READY: "green",
    FieldStatus.PARTIAL: "yellow",
    FieldStatus.DERIVE: "dark_orange",
    FieldStatus.NOT_FOUND: "red",
}
VERDICT_STYLE = {Verdict.FOUND: "green", Verdict.PARTIAL: "yellow", Verdict.NOT_FOUND: "red"}

SettingsOpt = typer.Option(
    None, "--settings", help="Ayar dosyası (varsayılan config/settings.yaml)"
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


def _load_engine(settings: Settings) -> Engine:
    try:
        engine = Engine.from_index(settings)
    except IndexMissingError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    source = Path(settings.dictionary.path)
    indexed = engine.index_meta.get("dictionary_version", "")
    if source.exists() and indexed:
        rows = int(indexed.rsplit("-", 1)[-1])
        if file_version(source, rows) != indexed:
            console.print(
                "[yellow]Uyarı: sözlük dosyası indeks kurulduktan sonra değişmiş. "
                "`vsa index` ile yeniden kurun.[/yellow]"
            )
    return engine


@app.command()
def index(
    dictionary: Path | None = typer.Option(None, "--dictionary", "-d", help="Sözlük .xlsx"),
    dense: bool = typer.Option(
        False, "--dense", help="Vektör indeksini de kur (embedding modeli gerekir, M3)"
    ),
    settings_path: Path | None = SettingsOpt,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Sözlükten arama indeksini kurar."""
    settings = _setup(settings_path, verbose)
    if dictionary:
        settings.dictionary.path = str(dictionary)
    with console.status("Sözlük okunuyor ve indeks kuruluyor…"):
        engine = Engine.from_dictionary_file(settings)
        meta = engine.save()
    if dense:
        _build_dense(engine, settings)
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


def _build_dense(engine: Engine, settings: Settings) -> None:
    model = settings.llm.embedding_model
    if not (settings.llm.endpoint and model):
        console.print("[red]llm.endpoint ve llm.embedding_model ayarlanmalı.[/red]")
        raise typer.Exit(2)
    client = OpenAICompatibleClient(settings.llm.endpoint, settings.llm.model, model, timeout=600)
    try:
        client.ping()
    except LLMError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    with Progress(
        TextColumn("Vektörler"), BarColumn(), MofNCompleteColumn(), TimeRemainingColumn(),
        console=console,
    ) as progress:  # fmt: skip
        task = progress.add_task("dense", total=len(engine.dictionary.columns))
        build_dense_index(
            engine.dictionary.columns,
            client,
            model,
            Path(settings.index.dir),
            progress=lambda done, total: progress.update(task, completed=done),
        )
    console.print(f"[green]Vektör indeksi hazır[/green] ({model})")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Dinlenecek adres"),
    port: int = typer.Option(8765, "--port", "-p"),
    open_browser: bool = typer.Option(False, "--open", help="Tarayıcıda aç"),
    settings_path: Path | None = SettingsOpt,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Web arayüzünü başlatır (M6)."""
    settings = _setup(settings_path, verbose)
    engine = _load_engine(settings)
    url = f"http://{host}:{port}"
    console.print(
        Panel.fit(
            f"[bold]{url}[/bold]\n"
            f"Anlamsal arama: {'açık' if engine.hybrid else 'kapalı'} · "
            f"LLM hakem: {engine.llm.model if engine.judge_enabled else 'kapalı'}\n"
            "Durdurmak için Ctrl+C",
            title="DWH Navigator",
            border_style="green",
        )
    )
    if open_browser:
        webbrowser.open(url)
    serve_app(engine, host, port, Path(settings.report.out_dir), FEEDBACK_PATH)


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
    query: str = typer.Argument(..., help="İş biriminin talebi"),
    top: int = typer.Option(5, "--top", "-n", help="En fazla kaç obje önerilsin"),
    no_excel: bool = typer.Option(False, "--no-excel", help="Excel üretme, yalnızca terminal"),
    out: Path | None = typer.Option(None, "--out", help="Rapor klasörü"),
    settings_path: Path | None = SettingsOpt,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Tek bir talebi analiz eder; Excel raporu üretir."""
    settings = _setup(settings_path, verbose)
    engine = _load_engine(settings)
    result = engine.analyze(query, top_n=top)
    _print_result(result)
    if not no_excel:
        path = write_ask_report(
            result, report_path(out or Path(settings.report.out_dir), "ask", query)
        )
        console.print(f"[green]Rapor:[/green] {path}")


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


def _print_batch(r: BatchResult) -> None:
    console.print(
        Panel(r.summary, title="Sonuç", border_style=VERDICT_STYLE[r.verdict], expand=False)
    )
    table = Table(show_lines=True, header_style="bold white on #1F3864")
    for col in ("#", "Talep Alanı", "Durum", "En İyi Eşleşme", "Güven"):
        table.add_column(col, justify="right" if col in ("#", "Güven") else "left")
    for fr in r.fields:
        style = STATUS_STYLE[fr.status]
        best = fr.best
        match = "-"
        if best is not None:
            match = f"[bold]{best.match.object_name}[/bold].{best.match.columns[0].col.column}"
            if best.derivation:
                match += f"{NL}[cyan]→ {best.derivation}[/cyan]"
        table.add_row(
            str(fr.field.index),
            f"{fr.field.tr}{NL}[dim]{fr.field.en}[/dim]",
            f"[{style}]{fr.status.value}[/{style}]",
            match,
            f"%{round(best.score * 100)}" if best else "-",
        )
    console.print(table)
    if r.coverage:
        c = r.coverage[0]
        console.print(
            f"[cyan]• Tek tablo kapsama:[/cyan] {c.object_name} — "
            f"{len(c.fields)}/{len(r.fields)} alan ({c.ready} hazır düzeyde)"
        )
    for n in r.notes:
        if n.scope == "Netleştirme":
            console.print(f"[cyan]• Netleştirme:[/cyan] {n.text}")
    console.print(f"[dim]{r.elapsed_ms} ms · sözlük {r.dictionary_version}[/dim]")


@app.command()
def batch(
    input_file: Path = typer.Option(..., "--input", "-i", help="Talep tablosu (.xlsx)"),
    sheet: str = typer.Option("0", "--sheet", help="Sayfa adı veya sırası"),
    top: int = typer.Option(3, "--top", "-n", help="Alan başına en fazla öneri"),
    no_excel: bool = typer.Option(False, "--no-excel", help="Excel üretme"),
    out: Path | None = typer.Option(None, "--out", help="Rapor klasörü"),
    settings_path: Path | None = SettingsOpt,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Hedef tablo talebini (TR başlık / EN başlık / açıklama) alan alan analiz eder."""
    settings = _setup(settings_path, verbose)
    fields = load_request_file(input_file, int(sheet) if sheet.isdigit() else sheet)
    if not fields:
        console.print("[red]Talep dosyasında alan bulunamadı.[/red]")
        raise typer.Exit(2)
    engine = _load_engine(settings)
    with console.status(f"{len(fields)} alan analiz ediliyor…"):
        result = BatchAnalyzer(engine, top_n=top).analyze(fields, input_file.stem)
    _print_batch(result)
    if not no_excel:
        path = write_batch_report(
            result, report_path(out or Path(settings.report.out_dir), "batch", input_file.stem)
        )
        console.print(f"[green]Rapor:[/green] {path}")


@app.command("eval")
def eval_cmd(
    golden: Path = typer.Option(Path("tests/golden_set.yaml"), "--golden"),
    negatives: Path = typer.Option(Path("tests/negative_set.yaml"), "--negatives"),
    compare: bool = typer.Option(False, "--compare", help="Genişletme varyantlarını karşılaştır"),
    save: bool = typer.Option(False, "--save", help="Metrikleri eval/history.jsonl'e ekle"),
    label: str = typer.Option("", "--label", help="Kayıt etiketi (ör. 'coverage v2')"),
    settings_path: Path | None = SettingsOpt,
) -> None:
    """Golden set ve negatif set üzerinde değerlendirme (HANDOVER §13)."""
    settings = _setup(settings_path)
    engine = _load_engine(settings)
    gold, negs = load_yaml_list(golden), load_yaml_list(negatives)

    if compare:
        with console.status("Konfigürasyonlar karşılaştırılıyor…") as status:
            results = compare_configs(engine, gold, negs, lambda n: status.update(n))
        table = Table(title="Konfigürasyon karşılaştırması (§13.4)",
                      header_style="bold white on #1F3864", title_justify="left")  # fmt: skip
        for col in ("Konfigürasyon", "ask R@1", "ask R@3", "ask MRR", "kolon",
                    "batch R@1", "batch R@3", "batch MRR", "tuzak", "yanlış cevap"):  # fmt: skip
            table.add_column(col, justify="right" if col != "Konfigürasyon" else "left")
        for name, r in results:
            table.add_row(
                name, f"{r.recall(1):.2f}", f"{r.recall(3):.2f}", f"{r.mrr():.3f}",
                f"{r.column_recall():.2f}", f"{r.recall(1, 'batch'):.2f}",
                f"{r.recall(3, 'batch'):.2f}", f"{r.mrr('batch'):.3f}",
                str(r.trap_violations), f"{r.false_answer_rate:.2f}",
            )  # fmt: skip
        console.print(table)
        return

    report = evaluate(engine, gold, negs)
    _print_items(report, "ask", "Serbest metin talepleri")
    _print_items(report, "batch", "Hedef tablo alanları (batch)")
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


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
