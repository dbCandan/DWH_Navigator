"""Command line interface (HANDOVER §14.1). Does I/O.

vsa index                      build the index from the dictionary
vsa ask "…" [--top 5] [--no-excel] [--out out/]
vsa eval                       golden-set metrics
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

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

from vsa import lab
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
from vsa.feedback import export_candidates, load_feedback, summarize
from vsa.index.dense import build_dense_index
from vsa.index.store import IndexMissingError
from vsa.llm.client import LLMError, OpenAICompatibleClient
from vsa.llm.judge import judge
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
    for col in ("Talep", "👍", "👎", "Alan oyları"):
        table.add_column(col)
    for fb in rows:
        table.add_row(
            fb.query[:70],
            NL.join(k.rsplit(".", 1)[-1] for k in fb.up) or "-",
            NL.join(k.rsplit(".", 1)[-1] for k in fb.down) or "-",
            str(len(fb.fields)) if fb.fields else "-",
        )
    console.print(table)
    n = export_candidates(FEEDBACK_PATH, export)
    console.print(
        f"[green]{n} aday golden madde yazıldı:[/green] {export} (gözden geçirip ekleyin)"
    )


LAB_RESULTS, LAB_PROGRESS, LAB_STOP = lab.RESULTS_PATH, lab.PROGRESS_PATH, lab.STOP_PATH


class _LabStopped(Exception):
    pass


def _lms_path() -> str:
    found = shutil.which("lms")
    return found or str(Path.home() / ".lmstudio" / "bin" / "lms.exe")


def _lms(*args: str, timeout: float = 900) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            [_lms_path(), *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def _lms_json(*args: str) -> list[dict[str, Any]]:
    ok, out = _lms(*args, "--json", timeout=60)
    try:
        data = json.loads(out) if ok else []
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _loaded_chat_models() -> list[str]:
    return [str(m.get("identifier", "")) for m in _lms_json("ps") if m.get("type") == "llm"]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _print_lab(results: dict[str, Any]) -> None:
    rows = lab.rank(results)
    if not rows:
        console.print("[yellow]Henüz ölçüm yok.[/yellow]")
        return
    table = Table(header_style="bold white on #1F3864", title="Model laboratuvarı")
    for col in ("", "Model", "T", "Düşünme", "Kalite", "Hakem", "Final", "Aynı seçim",
                "Aynı sıra", "Sapma", "sn/soru"):
        table.add_column(col, justify="right" if col not in ("Model", "Düşünme") else "left")
    for r in rows:
        table.add_row(
            "★" if r["recommended"] else "", r["model"], f"{r['temperature']:g}",
            r["reasoning_effort"] or "varsayılan", f"{r['quality']:.3f}",
            f"{r['judge_accuracy']:.2f}", f"{r['final_accuracy']:.2f}",
            f"{r['consistent_picks']:.2f}", f"{r['consistent_final_order']:.2f}",
            f"{r['mean_conf_drift']:.3f}", f"{r['mean_sec']:.1f}",
        )
    console.print(table)


@app.command("lab")
def lab_cmd(
    models: list[str] = typer.Argument(
        None, help="Model anahtarları (boşsa yüklü tüm sohbet modelleri)"
    ),
    temps: str = typer.Option("0,0.1", "--temps", help="Denenecek sıcaklıklar"),
    runs: int = typer.Option(2, "--runs", help="Her soru kaç kez sorulsun (tutarlılık)"),
    efforts: str = typer.Option("auto", "--effort", help="auto | none | low | …"),
    show: bool = typer.Option(False, "--list", help="Ölçmeden sonuç tablosunu göster"),
    settings_path: Path | None = SettingsOpt,
) -> None:
    """Hakem modellerini doğruluk + tutarlılık + hız için ölçer ve en iyisini önerir (ADR-025)."""
    settings = _setup(settings_path)
    results: dict[str, Any] = (
        json.loads(LAB_RESULTS.read_text(encoding="utf-8")) if LAB_RESULTS.exists() else {}
    )
    if show:
        _print_lab(results)
        return
    installed = _lms_json("ls")
    chat = [m["modelKey"] for m in installed if m.get("type") == "llm"]
    todo = list(models) if models else chat
    missing = [m for m in todo if m not in chat]
    if missing:
        console.print(f"[red]LM Studio'da yok: {', '.join(missing)}[/red]")
        raise typer.Exit(2)
    sizes = {m["modelKey"]: m.get("sizeBytes", 0) for m in installed}
    temperatures = [float(t) for t in temps.split(",") if t.strip()]

    s = load_settings(settings_path)
    s.llm.enabled = False  # candidates from rules + dense only; the judge is the variable
    engine = _load_engine(s)
    golden = load_yaml_list(Path("tests/golden_set.yaml"))
    negatives = load_yaml_list(Path("tests/negative_set.yaml"))
    cases = lab.build_cases(engine, golden, negatives, settings.llm.judge_candidates)
    counted = {c["id"] for c in cases if c["reachable"]}
    probe_case = next(c for c in cases if c["expected"] and c["reachable"])
    weights = (s.scoring.w_rule, s.scoring.w_llm)
    total = len(todo) * len(temperatures) * len(cases) * runs
    started = time.time()
    progress: dict[str, Any] = {
        "running": True, "pid": os.getpid(), "started": started, "done": 0, "total": total,
        "models": todo, "model": "", "step": "", "log": [],
        "cases": len(cases), "unreachable": [c["id"] for c in cases if not c["reachable"]],
    }

    def note(line: str) -> None:
        console.print(line)
        progress["log"] = [*progress["log"], line][-40:]
        progress["elapsed"] = round(time.time() - started)
        progress["updated"] = time.time()
        _write_json(LAB_PROGRESS, progress)

    def check_stop() -> None:
        if LAB_STOP.exists():
            LAB_STOP.unlink(missing_ok=True)
            raise _LabStopped

    LAB_STOP.unlink(missing_ok=True)

    note(f"{len(cases)} vaka ({len(counted)} ölçülebilir) × {runs} tekrar × "
         f"{len(temperatures)} sıcaklık × {len(todo)} model = {total} çağrı")
    previously = _loaded_chat_models()
    try:
        for model in todo:
            progress["model"] = model
            for other in _loaded_chat_models():
                if other != model:
                    _lms("unload", other)
            loaded = any(m.get("identifier") == model for m in _lms_json("ps"))
            t0 = time.time()
            ok = loaded
            if not loaded:
                note(f"▶ {model}: yükleniyor ({sizes.get(model, 0) / 1e9:.1f} GB)…")
                ok, out = _lms("load", model, "--context-length", "8192", "--gpu", "max", "-y")
                if not ok:  # does not fit the GPU entirely: let LM Studio split it
                    note(f"  tam GPU'ya sığmadı, otomatik bölüşüm deneniyor ({out[-120:]})")
                    ok, out = _lms("load", model, "--context-length", "8192", "-y")
            load_sec = round(time.time() - t0)
            if not ok:
                note(f"  ✗ {model} yüklenemedi: {out[-160:]}")
                results.setdefault(model, {})["load_error"] = {"error": out[-300:]}
                progress["done"] += len(temperatures) * len(cases) * runs
                continue
            note(f"  yüklendi ({load_sec} sn)")

            def client(temp: float, effort: str, m: str = model) -> OpenAICompatibleClient:
                return OpenAICompatibleClient(s.llm.endpoint, m, temperature=temp, timeout=900,
                                              api_key=s.llm.api_key, reasoning_effort=effort)

            if efforts == "auto":

                def probe(effort: str, m: str = model) -> bool:
                    t = time.time()
                    r = judge(probe_case["query"], probe_case["cands"], client(0.0, effort, m))
                    verdict = "geçerli" if r and r.verdicts else "boş/geçersiz"
                    note(f"  düşünme='{effort or 'varsayılan'}' denemesi: {verdict} "
                         f"({time.time() - t:.0f} sn)")
                    return bool(r and r.verdicts)

                effort = lab.pick_effort(probe)
                if effort is None:
                    note(f"  ✗ {model} hiçbir düşünme modunda geçerli JSON üretmedi")
                    results.setdefault(model, {})["load_error"] = {"error": "geçerli JSON yok"}
                    progress["done"] += len(temperatures) * len(cases) * runs
                    continue
                chosen = [effort]
            else:
                chosen = [e.strip() for e in efforts.split(",")]
            for effort in chosen:
                for temp in temperatures:
                    progress["step"] = f"T={temp:g}, düşünme={effort or 'varsayılan'}"
                    c = client(temp, effort)
                    rows: dict[str, list[dict[str, Any]]] = {}
                    for case in cases:
                        for run in range(runs):
                            check_stop()
                            t = time.time()
                            r = judge(case["query"], case["cands"], c)
                            conf = {k: v.confidence for k, v in r.verdicts.items()} if r else None
                            res = lab.score_reply(case, conf, r.unknown_ids if r else 0,
                                                  time.time() - t, *weights)
                            rows.setdefault(case["id"], []).append(res)
                            progress["done"] += 1
                            mark = "·" if case["id"] not in counted else "✗"
                            mark = "✓" if res["judge_ok"] else mark
                            note(f"  {mark} T={temp:g} {case['id']} #{run + 1} {res['sec']:.0f} sn "
                                 f"→ {', '.join(res['picks'][:2]) or '(seçim yok)'}")
                    summary = lab.summarize(rows, counted)
                    results.setdefault(model, {}).pop("load_error", None)
                    results[model][f"T{temp:g}|{effort}"] = {
                        "temperature": temp, "reasoning_effort": effort, "summary": summary,
                        "load_sec": load_sec, "size_gb": round(sizes.get(model, 0) / 1e9, 2),
                        "at": time.strftime("%Y-%m-%d %H:%M"), "cases": rows,
                    }
                    _write_json(LAB_RESULTS, results)
                    note(f"  ■ {model} T={temp:g}: kalite {lab.quality(summary):.3f}, hakem "
                         f"{summary['judge_accuracy']:.2f}, {summary['mean_sec']:.0f} sn/soru")
            _lms("unload", model)
    except _LabStopped:
        note("Kullanıcı durdurdu; tamamlanan ölçümler kaydedildi.")
    finally:
        # Leave LM Studio as we found it: the app's judge model loaded again.
        for m in previously or [s.llm.model]:
            if m and not any(x.get("identifier") == m for x in _lms_json("ps")):
                _lms("load", m, "--context-length", "8192", "--gpu", "max", "-y")
        progress["running"] = False
        progress["model"] = ""
        best = next((r for r in lab.rank(results) if r["recommended"]), None)
        keys = ("model", "temperature", "reasoning_effort")
        progress["best"] = best and {k: best[k] for k in keys}
        note("Bitti." if progress["done"] >= total else "Durduruldu.")
    _print_lab(results)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
