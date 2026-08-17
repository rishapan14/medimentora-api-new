import csv
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _make_csv_response(rows, headers, filename):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in headers})
    buffer = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    buffer.seek(0)
    return buffer, f"{filename}.csv", "text/csv"


def _make_pdf_response(title, headers, rows, filename):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 0.2 * inch),
        Paragraph(
            f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            styles["Normal"],
        ),
        Spacer(1, 0.3 * inch),
    ]

    table_data = [headers]
    for row in rows:
        table_data.append([str(row.get(header, "")) for header in headers])

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer, f"{filename}.pdf", "application/pdf"


def build_export_file(format_type, title, headers, rows, filename):
    fmt = (format_type or "csv").lower()
    if fmt == "pdf":
        return _make_pdf_response(title, headers, rows, filename)
    if fmt == "csv":
        return _make_csv_response(rows, headers, filename)
    raise ValueError("format must be csv or pdf")


def parse_csv_upload(file_storage):
    content = file_storage.read()
    if not content:
        return None, "Uploaded file is empty."

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "File must be a UTF-8 encoded CSV."

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return None, "CSV file must include a header row."

    rows = []
    for index, row in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in row.values()):
            continue
        normalized = {}
        for key, value in row.items():
            if key is None:
                continue
            normalized[key.strip()] = value.strip() if isinstance(value, str) else value
        rows.append({"_row": index, **normalized})
    if not rows:
        return None, "CSV file contains no data rows."

    return rows, None
