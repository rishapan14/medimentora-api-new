import os

from flask import current_app, request, send_file
from flask_jwt_extended import current_user

from app.constants import REPORT_TYPE_IMAGE, REPORT_TYPE_PDF
from app.extensions import db
from app.helpers.response import error_response, success_response
from app.models.report_model import Report
from app.services.upload_service import UploadService
from app.utils import save_upload_file, utc_now
from app.utils.ocr import extract_text as run_ocr
from app.validations.report_validation import validate_save_report


PDF_EXTENSIONS = {"pdf"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"}


def _collect_upload_files():
  """Collect files from multipart fields: files, files[], file."""
  files = []
  files.extend(request.files.getlist("files"))
  files.extend(request.files.getlist("files[]"))
  single = request.files.get("file")
  if single and single.filename:
    files.append(single)
  # Deduplicate by object identity while preserving order
  seen = set()
  unique = []
  for f in files:
    if f is None or id(f) in seen:
      continue
    seen.add(id(f))
    unique.append(f)
  return unique


def upload_multiple():
  """POST /api/reports/upload — accept multiple PDFs and images in one request."""
  files = _collect_upload_files()
  title = request.form.get("title")

  result = UploadService.upload_batch(
    user_id=current_user.id,
    files=files,
    title=title,
  )

  if not result.success:
    return error_response(
      "Upload validation failed.",
      400,
      {
        "success": False,
        "batch_id": result.batch_id,
        "errors": result.errors,
        "files_received": result.files_received,
      },
    )

  return success_response(
    f"{result.files_saved} file(s) uploaded successfully.",
    result.to_dict(),
    201,
  )


def upload_pdf():
  file = request.files.get("file")
  title = request.form.get("title", "Medical Report")

  file_path = save_upload_file(file, current_app.config["REPORT_UPLOAD_FOLDER"], PDF_EXTENSIONS)
  if not file_path:
    return error_response("Valid PDF file is required.", 400)

  report = Report(
    user_id=current_user.id,
    title=title,
    file_path=file_path,
    file_type=REPORT_TYPE_PDF,
    status="uploaded",
    original_filename=getattr(file, "filename", None),
    stored_filename=os.path.basename(file_path) if file_path else None,
    page_count=None,
  )
  db.session.add(report)
  db.session.commit()
  return success_response("PDF uploaded successfully.", {"report": report.to_dict()}, 201)


def upload_image():
  file = request.files.get("file")
  title = request.form.get("title", "Medical Report Image")

  file_path = save_upload_file(file, current_app.config["REPORT_UPLOAD_FOLDER"], IMAGE_EXTENSIONS)
  if not file_path:
    return error_response("Valid image file is required.", 400)

  report = Report(
    user_id=current_user.id,
    title=title,
    file_path=file_path,
    file_type=REPORT_TYPE_IMAGE,
    status="uploaded",
    original_filename=getattr(file, "filename", None),
    stored_filename=os.path.basename(file_path) if file_path else None,
    page_count=1,
  )
  db.session.add(report)
  db.session.commit()
  return success_response("Image uploaded successfully.", {"report": report.to_dict()}, 201)


def save_report():
  data = request.get_json(silent=True)
  errors = validate_save_report(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  report = Report(
    user_id=current_user.id,
    title=data["title"],
    file_path=data.get("file_path"),
    file_type=data.get("file_type", REPORT_TYPE_PDF),
    extracted_text=data.get("extracted_text"),
    status=data.get("status", "uploaded"),
  )
  db.session.add(report)
  db.session.commit()
  return success_response("Report saved.", {"report": report.to_dict()}, 201)


def extract_text(report_id):
  report = Report.query.filter_by(id=report_id, user_id=current_user.id).first()
  if not report:
    return error_response("Report not found.", 404)
  if not report.file_path:
    return error_response("Report has no file to extract text from.", 400)

  result = run_ocr(report.file_path, report.file_type)

  if not result.success:
    report.status = "failed"
    report.updated_at = utc_now()
    db.session.commit()
    status_code = 503 if result.error_code in ("ocr_not_available", "tesseract_not_installed") else 422
    return error_response(
      result.message or "OCR engine is not installed.",
      status_code,
      {
        **result.to_dict(),
        "success": False,
        "solution": result.solution
        or "Install RapidOCR in the Flask virtual environment, then restart with .venv\\Scripts\\python.exe run.py (or .\\start-api.ps1).",
      },
    )

  report.extracted_text = result.text
  report.status = "processed"
  report.updated_at = utc_now()
  if result.quality:
    report.ocr_confidence = float(result.quality.confidence)
    report.page_count = result.quality.page_count or report.page_count or len(result.pages) or 1
  elif result.pages:
    report.page_count = len(result.pages)
  db.session.commit()
  return success_response(
    "Text extracted successfully.",
    {"report": report.to_dict(include_text=True), **result.to_dict()},
  )


def list_reports():
  reports = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
  return success_response("Reports retrieved.", {"reports": [r.to_dict() for r in reports]})


def get_report(report_id):
  report = Report.query.filter_by(id=report_id, user_id=current_user.id).first()
  if not report:
    return error_response("Report not found.", 404)
  return success_response("Report retrieved.", {"report": report.to_dict()})


def delete_report(report_id):
  report = Report.query.filter_by(id=report_id, user_id=current_user.id).first()
  if not report:
    return error_response("Report not found.", 404)

  if report.file_path and os.path.exists(report.file_path):
    try:
      os.remove(report.file_path)
    except OSError:
      pass

  db.session.delete(report)
  db.session.commit()
  return success_response("Report deleted.")


def report_history():
  reports = Report.query.filter_by(user_id=current_user.id).order_by(Report.created_at.desc()).all()
  return success_response("Report history retrieved.", {
    "history": [r.to_dict() for r in reports],
    "total": len(reports),
  })
