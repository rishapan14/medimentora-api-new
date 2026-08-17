"""Merge OCR lines in correct reading order (supports multi-column layouts)."""

from __future__ import annotations

from app.services.report_analysis.ocr.engines.base import EngineLine


def merge_reading_order(lines: list[EngineLine], column_gap_ratio: float = 0.35) -> str:
    """
    Sort OCR boxes top-to-bottom, left-to-right with basic column detection.

    column_gap_ratio: horizontal gap threshold relative to page width for new column.
    """
    if not lines:
        return ""

    with_boxes = [ln for ln in lines if ln.box and len(ln.box) >= 4]
    if not with_boxes:
        return "\n".join(ln.text for ln in lines if ln.text.strip())

    enriched = []
    for ln in with_boxes:
        xs = [pt[0] for pt in ln.box]
        ys = [pt[1] for pt in ln.box]
        enriched.append(
            {
                "line": ln,
                "x_min": min(xs),
                "x_max": max(xs),
                "y_min": min(ys),
                "y_max": max(ys),
                "y_center": sum(ys) / len(ys),
                "x_center": sum(xs) / len(xs),
            }
        )

    page_width = max(item["x_max"] for item in enriched) or 1.0
    enriched.sort(key=lambda i: (i["y_center"], i["x_center"]))

    rows: list[list[dict]] = []
    row_threshold = max(12.0, page_width * 0.015)

    for item in enriched:
        placed = False
        for row in rows:
            if abs(row[0]["y_center"] - item["y_center"]) <= row_threshold:
                row.append(item)
                placed = True
                break
        if not placed:
            rows.append([item])

    ordered_text: list[str] = []
    for row in rows:
        row.sort(key=lambda i: i["x_center"])
        columns: list[list[dict]] = []
        for item in row:
            if not columns:
                columns.append([item])
                continue
            prev = columns[-1][-1]
            gap = item["x_min"] - prev["x_max"]
            if gap > page_width * column_gap_ratio:
                columns.append([item])
            else:
                columns[-1].append(item)

        for col in columns:
            col.sort(key=lambda i: i["y_center"])
            for item in col:
                text = item["line"].text.strip()
                if text:
                    ordered_text.append(text)

    return "\n".join(ordered_text)
