def validate_certificate(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("course_id"):
    errors.append("course_id is required.")
  return errors
