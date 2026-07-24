"""CSV report builder."""

import csv
import io
from typing import Any


def build_csv(headers: list[str], rows: list[list[Any]]) -> bytes:
    """Return UTF-8 encoded CSV bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([str(v) if v is not None else "" for v in row])
    return buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
