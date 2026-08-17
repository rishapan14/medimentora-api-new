def validate_discussion(data, partial=False):
  errors = []
  if not data and not partial:
    return ["Request body is required."]
  if not partial:
    if not data.get("title"):
      errors.append("title is required.")
    if not data.get("content"):
      errors.append("content is required.")
  return errors


def validate_comment(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("content"):
    errors.append("content is required.")
  return errors
