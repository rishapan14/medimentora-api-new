from app.constants import VALID_DIFFICULTIES


def validate_quiz(data, partial=False):
  errors = []
  if not data and not partial:
    return ["Request body is required."]
  if not partial and not data.get("title"):
    errors.append("title is required.")
  if data.get("difficulty") and data["difficulty"] not in VALID_DIFFICULTIES:
    errors.append(f"difficulty must be one of: {', '.join(VALID_DIFFICULTIES)}.")
  return errors


def validate_question(data, partial=False):
  errors = []
  if not data and not partial:
    return ["Request body is required."]
  if not partial:
    if not data.get("question_text"):
      errors.append("question_text is required.")
    if not data.get("options") or not isinstance(data["options"], list):
      errors.append("options must be a non-empty list.")
    if not data.get("correct_answer"):
      errors.append("correct_answer is required.")
  return errors


def validate_quiz_submit(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("answers") or not isinstance(data["answers"], dict):
    errors.append("answers must be a dictionary of question_id: answer.")
  return errors
