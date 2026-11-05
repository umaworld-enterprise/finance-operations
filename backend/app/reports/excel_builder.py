"""Excel report builder using openpyxl.

Rewritten 5 Nov 2026 after the client reported exports arriving "in raw
format, even numbers are not identified as Numbers (it is in text)". The
previous version wrote every cell with ``str(v)``, so amounts and dates
landed as text: no right alignment, no thousands separators, and SUM() over
a column returned nothing. Values now keep their real types and carry a
number format, and the sheet gets the usual reading aids — a styled header
band, frozen header row, autofilter and fitted columns.
"""

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
HEADER_HEIGHT = 26

MONEY_FORMAT = "#,##0.00"
INT_FORMAT = "#,##0"
DATE_FORMAT = "DD-MMM-YY"

_THIN = Side(style="thin", color="D9D9D9")
CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

# Widths are derived from the content, then clamped: narrow enough to stay
# readable on one screen, wide enough that a supplier name is not cut off.
MIN_WIDTH, MAX_WIDTH = 10, 46


def _coerce(value: Any) -> Any:
    """Return a value Excel will treat as its real type."""
    if value is None:
        return ""
    if isinstance(value, bool):          # bool is an int subclass — keep it readable
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float, datetime, date)):
        return value
    # Enums and anything else fall back to their printable form.
    return getattr(value, "value", None) or str(value)


def _number_format(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (datetime, date)):
        return DATE_FORMAT
    if isinstance(value, float):
        return MONEY_FORMAT
    if isinstance(value, int):
        return INT_FORMAT
    return None


def build_excel(title: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    """Generate an in-memory Excel workbook and return raw bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = (title or "Report")[:31]  # Sheet name limit

    ws.append(headers)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = CELL_BORDER
    ws.row_dimensions[1].height = HEADER_HEIGHT

    for row in rows:
        coerced = [_coerce(v) for v in row]
        ws.append(coerced)
        written = ws[ws.max_row]
        for cell, value in zip(written, coerced):
            fmt = _number_format(value)
            if fmt:
                cell.number_format = fmt
            # Text wraps at the column width instead of bleeding sideways.
            cell.alignment = Alignment(
                horizontal="right" if fmt and fmt != DATE_FORMAT else "left",
                vertical="top",
            )
            cell.border = CELL_BORDER

    # Fit each column to the longest rendered value, header included.
    for idx, header in enumerate(headers, start=1):
        longest = len(str(header))
        for row in rows:
            if idx - 1 < len(row):
                v = row[idx - 1]
                shown = (
                    f"{float(v):,.2f}" if isinstance(v, (Decimal, float))
                    else v.strftime("%d-%b-%y") if isinstance(v, (datetime, date))
                    else str(v if v is not None else "")
                )
                longest = max(longest, len(shown))
        ws.column_dimensions[get_column_letter(idx)].width = max(
            MIN_WIDTH, min(longest + 3, MAX_WIDTH)
        )

    # Header stays visible while scrolling, and every column is filterable.
    ws.freeze_panes = "A2"
    if headers and rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
