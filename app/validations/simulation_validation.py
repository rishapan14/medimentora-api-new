from app.constants import VALID_DIFFICULTIES


def validate_simulation(data, partial=False):
  errors = []
  if not data and not partial:
    return ["Request body is required."]
  if not partial:
    for field in ("title", "scenario", "correct_diagnosis", "correct_treatment"):
      if not data.get(field):
        errors.append(f"{field} is required.")
  if data.get("difficulty") and data["difficulty"] not in VALID_DIFFICULTIES:
    errors.append(f"difficulty must be one of: {', '.join(VALID_DIFFICULTIES)}.")
  return errors


def validate_simulation_attempt(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("diagnosis_selected"):
    errors.append("diagnosis_selected is required.")
  if not data.get("treatment_selected"):
    errors.append("treatment_selected is required.")
  return errors
