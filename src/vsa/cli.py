"""Command line interface (HANDOVER §14.1). Does I/O.

vsa index                      build the index from the dictionary
vsa ask "…" [--top 5] [--no-excel] [--out out/]
vsa eval                       golden-set metrics
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from vsa.config import Settings, load_settings
from vsa.evaluation import KS, evaluate, load_golden
from vsa.index.store import IndexMissingError
from vsa.loader import file_version
from vsa.models import AnalysisResult, Level, Verdict
from vsa.pipeline import Engine
from vsa.report.excel import report_path, write_ask_report

app = typer.Typer(add_completion=False, help="Veri Sözlüğü Asistanı (VSA)")
console = Console()

LEVEL_STYLE = {Level.HIGH: "green", Level.MEDIUM: "yellow", Level.LOW: "red"}
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


@app.command("eval")
def eval_cmd(
    golden: Path = typer.Option(Path("tests/golden_set.yaml"), "--golden"),
    settings_path: Path | None = SettingsOpt,
) -> None:
    """Golden set üzerinde recall@1/3/5 ve MRR hesaplar."""
    settings = _setup(settings_path)
    engine = _load_engine(settings)
    report = evaluate(engine, load_golden(golden))
    table = Table(header_style="bold white on #1F3864")
    for col in ("ID", "Sıra", "Birincil", "İlk 3"):
        table.add_column(col)
    for it in report.items:
        rank = str(it.rank) if it.rank else "[red]yok[/red]"
        prim = str(it.primary_rank) if it.primary_rank else "-"
        table.add_row(it.id, rank, prim, "\n".join(k.split(".")[-1] for k in it.top[:3]))
    console.print(table)
    metrics = "  ".join(f"recall@{k}={report.recall(k):.2f}" for k in KS)
    console.print(f"[bold]{metrics}  MRR={report.mrr:.3f}[/bold]  (n={len(report.items)})")


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
