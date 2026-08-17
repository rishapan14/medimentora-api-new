from app.constants import VALID_LMS_DIFFICULTIES


def validate_course(data, partial=False):
  errors = []
  if not data and not partial:
    return ["Request body is required."]
  if not partial and not data.get("title"):
    errors.append("title is required.")
  if data.get("difficulty") and data["difficulty"] not in VALID_LMS_DIFFICULTIES:
    errors.append(f"difficulty must be one of: {', '.join(VALID_LMS_DIFFICULTIES)}.")
  return errors


def validate_lesson(data, partial=False):
  errors = []
  if not data and not partial:
    return ["Request body is required."]
  if not partial:
    if not data.get("title"):
      errors.append("title is required.")
    if not data.get("course_id"):
      errors.append("course_id is required.")
  return errors
