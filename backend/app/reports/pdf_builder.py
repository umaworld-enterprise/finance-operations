"""PDF report builder using ReportLab."""

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_PAGE_W = landscape(A4)[0]
_MARGIN = 30


def _cell(value: Any, style: ParagraphStyle) -> Paragraph:
    text = str(value) if value is not None else ""
    # Escape XML special chars so ReportLab doesn't choke
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(text, style)


def build_pdf(
    title: str,
    headers: list[str],
    rows: list[list[Any]],
    col_widths: list[float] | None = None,
) -> bytes:
    """Return PDF bytes for a tabular report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=30, bottomMargin=30,
                            leftMargin=_MARGIN, rightMargin=_MARGIN)

    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        "HeaderCell",
        parent=styles["Normal"],
        fontSize=7.5,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        leading=10,
    )
    cell_style = ParagraphStyle(
        "DataCell",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=10,
    )

    usable_w = _PAGE_W - 2 * _MARGIN
    n = max(len(headers), 1)

    if col_widths is None:
        widths = [usable_w / n] * n
    else:
        # Scale caller's relative weights to usable page width
        total = sum(col_widths)
        widths = [w / total * usable_w for w in col_widths]

    # Build table data with Paragraph cells (enables real word-wrap)
    header_row = [_cell(h, header_style) for h in headers]
    data_rows = [
        [_cell(v, cell_style) for v in row]
        for row in rows
    ]
    table_data = [header_row] + data_rows

    table = Table(table_data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EBF3FB")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ])
    )

    story = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 12),
        table,
    ]
    doc.build(story)
    return buf.getvalue()
