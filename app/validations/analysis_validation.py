def validate_analysis(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("report_text") and not data.get("report_id"):
    errors.append("report_text or report_id is required.")
  return errors
