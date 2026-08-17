from app.constants import REPORT_TYPE_IMAGE, REPORT_TYPE_PDF


def validate_save_report(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("title"):
    errors.append("title is required.")
  file_type = data.get("file_type")
  if file_type and file_type not in (REPORT_TYPE_PDF, REPORT_TYPE_IMAGE):
    errors.append("file_type must be 'pdf' or 'image'.")
  return errors


def validate_extract_text(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("report_id") and not data.get("text"):
    errors.append("report_id or text is required.")
  return errors
