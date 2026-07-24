"""PDF report builder using ReportLab."""

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_pdf(title: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    """Return PDF bytes for a tabular report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=30, bottomMargin=30)

    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 12))

    # Table data
    data = [headers] + [[str(v) if v is not None else "" for v in row] for row in rows]

    col_width = (landscape(A4)[0] - 60) / max(len(headers), 1)
    table = Table(data, colWidths=[col_width] * len(headers), repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EBF3FB")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("WORDWRAP", (0, 0), (-1, -1), True),
        ])
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()
