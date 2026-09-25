"""Excel analysis report for ``ask`` mode (HANDOVER §12.1, §12.2). Does file I/O.

Sheets: Özet · Öneriler · Alan Detayları · Notlar ve Öneriler
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from vsa.models import (
    AnalysisResult,
    BatchResult,
    DictColumn,
    FieldStatus,
    FlagKind,
    Level,
    Note,
    Verdict,
)
from vsa.scoring.combine import level_for
from vsa.text.normalize import fold

CellValue = str | int | float | None

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF")
BODY_FONT = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
TITLE_FONT = Font(name=FONT, size=14, bold=True, color="1F3864")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")

LEVEL_FILL = {
    Level.HIGH: PatternFill("solid", fgColor="C6EFCE"),
    Level.MEDIUM: PatternFill("solid", fgColor="FFEB9C"),
    Level.LOW: PatternFill("solid", fgColor="FFC7CE"),
}
VERDICT_FILL = {
    Verdict.FOUND: PatternFill("solid", fgColor="C6EFCE"),
    Verdict.PARTIAL: PatternFill("solid", fgColor="FFEB9C"),
    Verdict.NOT_FOUND: PatternFill("solid", fgColor="FFC7CE"),
}

FLAG_LABEL = {
    FlagKind.MODEL_ESTIMATED: "Model tahmini — doğrulanmalı",
    FlagKind.CORRECTED: "Kaynak açıklama düzeltildi",
    FlagKind.NEEDS_VERIFICATION: "Doğrulanmalı",
    FlagKind.NAMING_MISMATCH: "İsim/içerik uyumsuzluğu",
    FlagKind.QUALITY_NOTE: "Kalite notu",
}


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", fold(text[:limit])).strip("_")
    return slug or "talep"


def report_path(out_dir: Path, mode: str, query: str, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M")
    return out_dir / f"VSA_{mode}_{slugify(query)}_{stamp}.xlsx"


def _table(
    ws: Worksheet,
    start_row: int,
    headers: Sequence[str],
    rows: Sequence[Sequence[CellValue]],
    widths: Sequence[int] | None = None,
) -> int:
    """Write a styled table; returns the next free row."""
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, BORDER
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for r, row in enumerate(rows, start_row + 1):
        for c, value in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.font, cell.border, cell.alignment = BODY_FONT, BORDER, WRAP
    if widths:
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
    return start_row + len(rows) + 1


def _finish_sheet(ws: Worksheet, header_row: int, n_cols: int, n_rows: int) -> None:
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = f"A{header_row + 1}"
    if n_rows:
        last = get_column_letter(n_cols)
        ws.auto_filter.ref = f"A{header_row}:{last}{header_row + n_rows}"


def _summary(ws: Worksheet, r: AnalysisResult) -> None:
    ws.title = "Özet"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 100
    ws["A1"] = "Veri Sözlüğü Asistanı — Analiz Raporu"
    ws["A1"].font = TITLE_FONT
    info = [
        ("Kaynak sözlük", f"{r.dictionary_source} (sürüm {r.dictionary_version})"),
        ("Üretim tarihi", r.generated_at),
        ("Talep", r.query),
        ("Genel sonuç", r.summary),
    ]
    row = 3
    for label, value in info:
        ws.cell(row=row, column=1, value=label).font = BOLD
        cell = ws.cell(row=row, column=2, value=value)
        cell.font, cell.alignment = BODY_FONT, WRAP
        if label == "Genel sonuç":
            cell.fill = VERDICT_FILL[r.verdict]
            cell.font = BOLD
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Güven skoru ölçeği").font = BOLD
    row = _table(
        ws,
        row + 1,
        ["Seviye", "Anlamı"],
        [
            ["Yüksek (%80–100)", "Alan adı veya açıklaması sorulan kavramla doğrudan örtüşüyor"],
            ["Orta (%50–79)", "İlişkili; kapsam, granülerlik veya tanım farkı var"],
            ["Düşük (%0–49)", "Dolaylı ilişki; sorulan veri bu alandan türetilebilir"],
        ],
    )
    for i, lvl in enumerate(Level):
        ws.cell(row=row - 3 + i, column=1).fill = LEVEL_FILL[lvl]

    row += 1
    ws.cell(row=row, column=1, value="Yöntem notları").font = BOLD
    notes = [
        *r.method,
        "Talep kavramları: " + (", ".join(r.concepts) or "-"),
        "Genişletme terimleri: " + (", ".join(r.expansion_terms) or "-"),
        f"Sözlük doğrulaması: {r.dropped_by_validation} alan düşürüldü",
        f"Süre: {r.elapsed_ms} ms",
    ]
    for n in notes:
        row += 1
        cell = ws.cell(row=row, column=2, value=n)
        cell.font, cell.alignment = BODY_FONT, WRAP


def _suggestions(ws: Worksheet, r: AnalysisResult) -> None:
    headers = [
        "Sıra", "Veritabanı", "Şema", "Obje", "Veri Seti Grubu", "İlgili Alanlar",
        "Gerekçe", "Kısıt / Dikkat", "Güven Skoru", "Güven Seviyesi", "Kullanım Önerisi",
    ]  # fmt: skip
    rows = [
        [
            i,
            m.database,
            m.schema,
            m.object_name,
            ", ".join(m.dataset_groups) or "-",
            "\n".join(h.col.column for h in m.columns),
            m.reason,
            m.caveat,
            round(m.score, 4),
            m.level.value,
            m.usage,
        ]
        for i, m in enumerate(r.objects, 1)
    ]
    if not rows:
        rows = [["-", "-", "-", "-", "-", "-", r.summary, "-", 0, "-", "-"]]
    _table(ws, 1, headers, rows, [6, 12, 8, 34, 22, 34, 60, 60, 11, 12, 40])
    for i in range(2, len(rows) + 2):
        ws.cell(row=i, column=9).number_format = "0%"
        level = ws.cell(row=i, column=10).value
        for lvl in Level:
            if level == lvl.value:
                ws.cell(row=i, column=10).fill = LEVEL_FILL[lvl]
    _finish_sheet(ws, 1, len(headers), len(rows))


def _field_details(ws: Worksheet, r: AnalysisResult) -> None:
    headers = ["Sıra", "Obje", "Alan Adı", "Sözlük Açıklaması", "Eş Anlamlılar", "Kalite Bayrağı"]
    rows: list[list[CellValue]] = []
    for i, m in enumerate(r.objects, 1):
        for h in m.columns:
            flags = "\n".join(
                f"{FLAG_LABEL[f.kind]}: {f.text}"
                if f.kind is not FlagKind.MODEL_ESTIMATED
                else FLAG_LABEL[f.kind]
                for f in h.col.flags
            )
            rows.append(
                [
                    i,
                    m.object_key,
                    h.col.column,
                    h.col.description,
                    ", ".join(h.col.synonyms) or "-",
                    flags or "-",
                ]
            )
    _table(ws, 1, headers, rows, [6, 40, 30, 80, 40, 40])
    _finish_sheet(ws, 1, len(headers), len(rows))


def _notes(ws: Worksheet, r: AnalysisResult) -> None:
    headers = ["Kapsam", "Başlık", "Açıklama"]
    rows = [[n.scope, n.title, n.text] for n in r.notes]
    _table(ws, 1, headers, rows, [18, 40, 100])
    _finish_sheet(ws, 1, len(headers), len(rows))


def write_ask_report(result: AnalysisResult, path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    _summary(ws, result)
    _suggestions(wb.create_sheet("Öneriler"), result)
    _field_details(wb.create_sheet("Alan Detayları"), result)
    _notes(wb.create_sheet("Notlar ve Öneriler"), result)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# --------------------------------------------------------------------------- batch (§12.3)

STATUS_FILL = {
    FieldStatus.READY: PatternFill("solid", fgColor="C6EFCE"),
    FieldStatus.PARTIAL: PatternFill("solid", fgColor="FFEB9C"),
    FieldStatus.DERIVE: PatternFill("solid", fgColor="FCE4D6"),
    FieldStatus.NOT_FOUND: PatternFill("solid", fgColor="FFC7CE"),
}
STATUS_MEANING = {
    FieldStatus.READY: "En iyi eşleşme ≥ %80 ve türetme gerektirmiyor",
    FieldStatus.PARTIAL: "%50–79, veya ≥ %80 ama kapsam/format farkı var",
    FieldStatus.DERIVE: "Hazır kolon yok; işlem seviyesi tablodan hesaplanabilir",
    FieldStatus.NOT_FOUND: "Tüm adaylar eşiğin altında",
}


def _fill_column(ws: Worksheet, col: int, first: int, last: int) -> None:
    for row in range(first, last + 1):
        value = ws.cell(row=row, column=col).value
        for status, fill in STATUS_FILL.items():
            if value == status.value:
                ws.cell(row=row, column=col).fill = fill
        for lvl, fill in LEVEL_FILL.items():
            if value == lvl.value:
                ws.cell(row=row, column=col).fill = fill


def _batch_summary(ws: Worksheet, r: BatchResult) -> None:
    ws.title = "Özet"
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Veri Sözlüğü Asistanı — Hedef Tablo Analizi"
    ws["A1"].font = TITLE_FONT
    info = [
        ("Kaynak sözlük", f"{r.dictionary_source} (sürüm {r.dictionary_version})"),
        ("Üretim tarihi", r.generated_at),
        ("Talep", r.name),
        ("Zaman düzeyi", r.time_grain or "-"),
        ("Genel sonuç", r.summary),
    ]
    row = 3
    for label, value in info:
        ws.cell(row=row, column=1, value=label).font = BOLD
        cell = ws.cell(row=row, column=2, value=value)
        cell.font, cell.alignment = BODY_FONT, WRAP
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
        if label == "Genel sonuç":
            cell.fill, cell.font = VERDICT_FILL[r.verdict], BOLD
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Alan bazında durum").font = BOLD
    status_rows: list[list[CellValue]] = []
    for fr in r.fields:
        best = fr.best
        match = (
            f"{best.match.object_name}.{best.match.columns[0].col.column}"
            + (f"  →  {best.derivation}" if best.derivation else "")
            if best
            else "-"
        )
        status_rows.append(
            [fr.field.index, fr.field.tr, fr.field.en, fr.status.value, match,
             round(best.score, 4) if best else 0]
        )  # fmt: skip
    start = row + 1
    status_headers = ["#", "Talep Alanı (TR)", "Talep Alanı (EN)", "Durum", "En İyi Eşleşme"]
    row = _table(ws, start, [*status_headers, "Güven"], status_rows)
    for i in range(start + 1, row):
        ws.cell(row=i, column=6).number_format = "0%"
    _fill_column(ws, 4, start + 1, row - 1)

    row += 1
    ws.cell(row=row, column=1, value="Tek tablo kapsama").font = BOLD
    cov_rows: list[list[CellValue]] = [
        [c.object_name, f"{len(c.fields)} / {len(r.fields)}", c.ready, ", ".join(c.fields)]
        for c in r.coverage
    ]
    row = _table(ws, row + 1, ["Obje", "Karşılanan alan", "Hazır düzeyde", "Alanlar"], cov_rows)

    row += 1
    ws.cell(row=row, column=1, value="Durum ölçeği").font = BOLD
    start = row + 1
    row = _table(
        ws, start, ["Durum", "Anlamı"], [[s.value, STATUS_MEANING[s]] for s in FieldStatus]
    )
    _fill_column(ws, 1, start + 1, row - 1)

    row += 1
    ws.cell(row=row, column=1, value="Yöntem notları").font = BOLD
    for n in r.method:
        row += 1
        cell = ws.cell(row=row, column=2, value=n)
        cell.font, cell.alignment = BODY_FONT, WRAP
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
    for col, width in zip("ABCDEF", (24, 30, 30, 16, 60, 10), strict=True):
        ws.column_dimensions[col].width = width


def _field_matching(ws: Worksheet, r: BatchResult) -> None:
    headers = [
        "#", "Talep Alanı (TR)", "Talep Alanı (EN)", "Talep Açıklaması", "Durum",
        "Öneri Sırası", "Obje", "Veri Seti Grubu", "Önerilen Alan(lar)", "Türetme",
        "Gerekçe", "Kısıt / Dikkat", "Güven", "Seviye",
    ]  # fmt: skip
    rows: list[list[CellValue]] = []
    for fr in r.fields:
        f = fr.field
        if not fr.candidates:
            rows.append([f.index, f.tr, f.en, f.description, fr.status.value, "-", "-", "-",
                         "-", "-", "Sözlükte karşılığı bulunamadı.", "-", 0, "-"])  # fmt: skip
            continue
        for rank, c in enumerate(fr.candidates, 1):
            m = c.match
            caveat = "\n".join(x for x in [*c.notes, m.caveat] if x and x != "-") or "-"
            rows.append(
                [
                    f.index, f.tr, f.en, f.description,
                    fr.status.value if rank == 1 else "",
                    rank, m.object_key, ", ".join(m.dataset_groups) or "-",
                    "\n".join(h.col.column for h in m.columns[:5]),
                    c.derivation or "-", m.reason, caveat,
                    round(c.score, 4), level_for(c.score).value,
                ]
            )  # fmt: skip
    _table(ws, 1, headers, rows, [5, 24, 26, 36, 13, 7, 40, 20, 32, 30, 60, 60, 8, 9])
    for i in range(2, len(rows) + 2):
        ws.cell(row=i, column=13).number_format = "0%"
    _fill_column(ws, 5, 2, len(rows) + 1)
    _fill_column(ws, 14, 2, len(rows) + 1)
    _finish_sheet(ws, 1, len(headers), len(rows))


def _batch_details(ws: Worksheet, r: BatchResult) -> None:
    seen: dict[str, tuple[str, DictColumn]] = {}
    for fr in r.fields:
        for c in fr.candidates:
            for h in c.match.columns[:5]:
                seen.setdefault(h.col.key, (c.match.object_key, h.col))
    rows: list[list[CellValue]] = []
    for obj, col in seen.values():
        flags = "\n".join(FLAG_LABEL[f.kind] for f in col.flags) or "-"
        rows.append([obj, col.column, col.description, ", ".join(col.synonyms) or "-", flags])
    headers = ["Obje", "Alan Adı", "Sözlük Açıklaması", "Eş Anlamlılar", "Kalite Bayrağı"]
    _table(ws, 1, headers, rows, [40, 32, 80, 40, 30])
    _finish_sheet(ws, 1, len(headers), len(rows))


def _notes_sheet(ws: Worksheet, notes: Sequence[Note]) -> None:
    headers = ["Kapsam", "Başlık", "Açıklama"]
    rows: list[list[CellValue]] = [[n.scope, n.title, n.text] for n in notes]
    _table(ws, 1, headers, rows, [18, 40, 100])
    _finish_sheet(ws, 1, len(headers), len(rows))


def write_batch_report(result: BatchResult, path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    _batch_summary(ws, result)
    _field_matching(wb.create_sheet("Alan Eşleştirme"), result)
    _batch_details(wb.create_sheet("Alan Detayları"), result)
    _notes_sheet(wb.create_sheet("Notlar ve Öneriler"), result.notes)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
