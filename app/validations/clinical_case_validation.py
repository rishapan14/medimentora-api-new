from app.constants import VALID_DIFFICULTIES


def validate_clinical_case(data, partial=False):
  errors = []
  if not data and not partial:
    return ["Request body is required."]
  if not partial:
    if not data.get("title"):
      errors.append("title is required.")
    if not data.get("disease"):
      errors.append("disease is required.")
  if data.get("difficulty") and data["difficulty"] not in VALID_DIFFICULTIES:
    errors.append(f"difficulty must be one of: {', '.join(VALID_DIFFICULTIES)}.")
  return errors
