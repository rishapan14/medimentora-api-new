def validate_notification(data):
  errors = []
  if not data:
    return ["Request body is required."]
  for field in ("notification_type", "title", "message"):
    if not data.get(field):
      errors.append(f"{field} is required.")
  return errors
