"""The single-question Excel report: Özet · Öneriler. Built in memory and returned as
bytes; nothing is written to disk (question-analysis Requirement 16). The term-list report
belongs to the list-search PRD.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell.cell import Cell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.analysis import AnalysisResult, Level, ObjectMatch, Verdict
from app.domain.turkish_text import fold

CellValue = str | int | float | None

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF")
BODY_FONT = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
TITLE_FONT = Font(name=FONT, size=14, bold=True, color="1F3864")
SECTION_FONT = Font(name=FONT, size=11, bold=True, color="1F3864")
SMALL_FONT = Font(name=FONT, size=9, color="595959")
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


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", fold(text[:limit])).strip("_")
    return slug or "talep"


def report_filename(mode: str, query: str, at: datetime) -> str:
    """``VSA_<mode>_<topic>_<YYYYMMDD_HHMM>.xlsx``; ``at`` is the caller's Istanbul time."""
    stamp = at.strftime("%Y%m%d_%H%M")
    return f"VSA_{mode}_{slugify(query)}_{stamp}.xlsx"


def _text(cell: Cell) -> Cell:
    """Keep a text that starts with "=" a text: openpyxl would write it as a formula, and a
    question or a model's sentence must never run in Excel (formula injection)."""
    if cell.data_type == "f":
        cell.data_type = "s"
    return cell


def _put(ws: Worksheet, row: int, column: int, value: CellValue) -> Cell:
    return _text(ws.cell(row=row, column=column, value=value))


def _table(
    ws: Worksheet,
    start_row: int,
    headers: Sequence[str],
    rows: Sequence[Sequence[CellValue]],
    widths: Sequence[int] | None = None,
) -> int:
    """Write a styled table; returns the next free row."""
    for c, h in enumerate(headers, 1):
        cell = _put(ws, start_row, c, h)
        cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, BORDER
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for r, row in enumerate(rows, start_row + 1):
        for c, value in enumerate(row, 1):
            cell = _put(ws, r, c, value)
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


def _merged(ws: Worksheet, row: int, first: int, last: int, value: CellValue) -> Cell:
    """Value across merged cells ``first..last`` of a row, wrapped."""
    cell = _put(ws, row, first, value)
    cell.font, cell.alignment = BODY_FONT, WRAP
    if last > first:
        ws.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
    return cell


def _grow(ws: Worksheet, row: int, text: str, chars_per_line: int) -> None:
    """Merged cells do not auto-size in Excel: give long texts room."""
    lines = sum(max(1, -(-len(part) // chars_per_line)) for part in text.split("\n"))
    ws.row_dimensions[row].height = max(15, 14 * lines)


def _section(ws: Worksheet, row: int, title: str) -> int:
    ws.cell(row=row, column=1, value=title).font = SECTION_FONT
    return row + 1


def _covers(m: ObjectMatch) -> str:
    if m.covers:
        return m.covers
    return ", ".join(m.covered) or ", ".join(h.col.column for h in m.columns[:4])


WARN_FILL = PatternFill("solid", fgColor="FFEB9C")


def answered_by(r: AnalysisResult) -> str:
    """Who wrote the answer, said plainly (ADR-034)."""
    if r.analyst:
        return f"Analist (dil modeli: {r.llm_model})"
    if r.fallback:
        return f"Analiz yapılamadı — {r.fallback}"
    cut = f"güven skorları %{round((1 - r.confidence_factor) * 100)} düşürülerek gösteriliyor"
    return f"Kural motoru (yalnız ölçüm amaçlı; kullanıcıya gösterilmez) — {cut}."


def _dictionary_line(r: AnalysisResult) -> str:
    rows = r.dictionary_version.rsplit("-", 1)[-1]
    size = f"{int(rows):,}".replace(",", ".") + " satır" if rows.isdigit() else r.dictionary_version
    objects = f", {r.dictionary_objects} obje" if r.dictionary_objects else ""
    return f"Kaynak sözlük: {r.dictionary_source} ({size}{objects})"


def _summary(ws: Worksheet, r: AnalysisResult) -> None:
    """Özet: request, verdict, reading of the request, suggestion table, confidence scale."""
    ws.title = "Özet"
    ws.sheet_view.showGridLines = False
    for col, width in zip("ABCDE", (16, 46, 70, 10, 12), strict=True):
        ws.column_dimensions[col].width = width
    ws["A1"] = "Veri Ambarı Veri Sözlüğü – İş Birimi Talep Analizi"
    ws["A1"].font = TITLE_FONT
    _merged(ws, 2, 1, 3, _dictionary_line(r)).font = SMALL_FONT
    stamp = datetime.fromisoformat(r.generated_at).strftime("%d.%m.%Y %H:%M")
    _merged(ws, 2, 4, 5, f"Üretim: {stamp}").font = SMALL_FONT
    by = _merged(ws, 3, 1, 5, f"Cevabı üreten: {answered_by(r)}")  # ADR-034
    by.font = SMALL_FONT
    if not r.analyst:
        by.fill = WARN_FILL

    row = 5
    info = [("Talep", r.query), ("Sonuç", r.summary)]
    if r.missing:
        info.append(("Eksik Bilgi", ", ".join(r.missing)))
    if r.interpretation:
        info.append(("Talebin Yorumu", r.interpretation))
    for label, value in info:
        ws.cell(row=row, column=1, value=label).font = BOLD
        ws.cell(row=row, column=1).alignment = WRAP
        cell = _merged(ws, row, 2, 5, value)
        _grow(ws, row, value, 120)
        if label == "Sonuç":
            cell.fill, cell.font = VERDICT_FILL[r.verdict], BOLD
        row += 1

    row = _section(ws, row + 1, "Öneri Özeti")
    rows: list[list[CellValue]] = [
        [i, m.object_key, _covers(m), round(m.score, 2), m.level.value]
        for i, m in enumerate(r.objects, 1)
    ]
    if not rows:
        rows = [["-", "Sözlükte karşılığı bulunamadı", "-", "-", "-"]]
    start = row
    headers = ["Sıra", "Veritabanı.Şema.Obje", "Kapsadığı Bilgi", "Güven", "Seviye"]
    row = _table(ws, start, headers, rows)
    for i in range(start + 1, row):
        ws.cell(row=i, column=4).number_format = "0.00"
        for lvl in Level:
            if ws.cell(row=i, column=5).value == lvl.value:
                ws.cell(row=i, column=5).fill = LEVEL_FILL[lvl]

    row = _section(ws, row + 1, "Güven Skoru Ölçeği")
    start = row
    _table(
        ws,
        start,
        ["Seviye", "Aralık", "Anlamı"],
        [
            ["Yüksek", "%80–100", "Alan adı veya açıklaması sorulan kavramla doğrudan örtüşüyor."],
            ["Orta", "%50–79", "Anlam olarak ilişkili; kapsam, granülerlik veya tanım farkı var."],
            ["Düşük", "%0–49", "Dolaylı ilişki var; sorulan veri bu alandan türetilebilir."],
        ],
    )
    for i, lvl in enumerate(Level):
        ws.cell(row=start + 1 + i, column=1).fill = LEVEL_FILL[lvl]


def _suggestions(ws: Worksheet, r: AnalysisResult) -> None:
    headers = [
        "Sıra", "Veritabanı", "Şema", "Obje", "Veri Seti Grubu", "İlgili Alanlar",
        "Gerekçe", "Kısıt / Dikkat", "Güven Skoru", "Güven Seviyesi", "Kullanım Önerisi",
    ]  # fmt: skip
    ws["A1"] = f"Öneriler – Güven Skoruna Göre İlk {max(len(r.objects), 1)}"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Talep:"
    ws["A2"].font, _put(ws, 2, 2, r.query).font = BOLD, BODY_FONT
    rows: list[list[CellValue]] = [
        [
            i,
            m.database,
            m.schema,
            m.object_name,
            ", ".join(m.dataset_groups) or "-",
            "\n".join(h.col.column for h in m.columns),
            m.reason,
            m.caveat,
            round(m.score, 2),
            m.level.value,
            m.usage,
        ]
        for i, m in enumerate(r.objects, 1)
    ]
    if not rows:
        rows = [["-", "-", "-", "-", "-", "-", r.summary, "-", 0, "-", "-"]]
    header_row = 3
    _table(ws, header_row, headers, rows, [6, 10, 8, 30, 20, 30, 70, 60, 10, 11, 40])
    for i in range(header_row + 1, header_row + len(rows) + 1):
        ws.cell(row=i, column=9).number_format = "0.00"
        level = ws.cell(row=i, column=10).value
        for lvl in Level:
            if level == lvl.value:
                ws.cell(row=i, column=10).fill = LEVEL_FILL[lvl]
    _finish_sheet(ws, header_row, len(headers), len(rows))


def write_ask_report(result: AnalysisResult) -> bytes:
    wb = Workbook()
    ws = wb.active
    if not isinstance(ws, Worksheet):
        raise TypeError("yeni çalışma kitabının sayfası yok")
    _summary(ws, result)
    _suggestions(wb.create_sheet("Öneriler"), result)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
