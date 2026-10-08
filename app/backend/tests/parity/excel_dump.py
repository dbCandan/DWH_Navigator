"""The single-question report as data, read back with openpyxl (3.1.5 on both sides).

Compared are the sheet names and order, every cell's value and type, font, fill, border,
alignment and number format, merged cells, column widths, row heights, the frozen pane, the
filter and the grid lines. The package's creation data (zip times, document properties) is
not read: question-analysis Requirement 2 leaves it out of the comparison. A reason text that
Requirement 5 changes on purpose is masked, and so is the height of a row holding it (the
report sizes a row by its text).
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from tests.parity.dump import MASK


def _color(color: Any) -> Any:
    if color is None:
        return None
    return [color.type, str(color.rgb) if color.type == "rgb" else color.value, color.tint]


def _side(side: Any) -> Any:
    return [side.style, _color(side.color)]


def _value(value: Any, reason: str) -> Any:
    if isinstance(value, str) and reason:
        value = value.replace(reason, MASK)
    return [type(value).__name__, value]


def _holds(value: Any, reason: str) -> bool:
    return bool(reason) and isinstance(value, str) and reason in value


def workbook(data: bytes, reason: str = "") -> dict[str, Any]:
    book = load_workbook(BytesIO(data))
    sheets = []
    for ws in book.worksheets:
        cells = []
        masked_rows = set()
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
            for cell in row:
                if cell.value is None and not cell.has_style:
                    continue
                if _holds(cell.value, reason):
                    masked_rows.add(cell.row)
                font, fill, border, align = cell.font, cell.fill, cell.border, cell.alignment
                cells.append(
                    [
                        cell.coordinate,
                        _value(cell.value, reason),
                        cell.data_type,
                        cell.number_format,
                        [font.name, font.sz, font.b, font.i, font.u, _color(font.color)],
                        [fill.fill_type, _color(fill.fgColor), _color(fill.bgColor)],
                        [_side(s) for s in (border.left, border.right, border.top, border.bottom)],
                        [align.horizontal, align.vertical, align.wrap_text],
                    ]
                )
        sheets.append(
            {
                "title": ws.title,
                "grid_lines": ws.sheet_view.showGridLines,
                "freeze": ws.freeze_panes,
                "filter": ws.auto_filter.ref,
                "merged": sorted(str(r) for r in ws.merged_cells.ranges),
                "widths": sorted(
                    [k, d.width] for k, d in ws.column_dimensions.items() if d.customWidth
                ),
                "heights": sorted(
                    [k, MASK if k in masked_rows else d.height]
                    for k, d in ws.row_dimensions.items()
                    if d.height is not None
                ),
                "dimensions": ws.dimensions,
                "cells": cells,
            }
        )
    return {"sheets": book.sheetnames, "content": sheets}
