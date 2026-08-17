"""Verify report history schema after patches."""
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.helpers.schema_patches import ensure_report_history_schema

REQUIRED = {
    "id",
    "user_id",
    "original_filename",
    "stored_filename",
    "file_path",
    "file_type",
    "file_size",
    "report_type",
    "extracted_text",  # ocr_text
    "structured_json",
    "ocr_confidence",
    "analysis_confidence",
    "analysis_date",
    "status",
    "created_at",  # upload_date
    "updated_at",
    "page_count",
}

app = create_app()
with app.app_context():
    ensure_report_history_schema()
    cols = {c["name"] for c in inspect(db.engine).get_columns("reports")}
    missing = sorted(REQUIRED - cols)
    print("=== reports columns after patch ===")
    for name in sorted(cols):
        mark = "OK" if name in REQUIRED or name in {"title", "batch_id"} else "  "
        print(f"  [{mark}] {name}")
    print()
    if missing:
        print("MISSING:", missing)
        raise SystemExit(1)
    print("All required history columns present.")
    # soft-delete note
    print("Note: analysis_result lives in report_analysis.full_response (linked by report_id).")
    print("Note: upload_date is exposed as created_at / upload_date in API serialization.")
