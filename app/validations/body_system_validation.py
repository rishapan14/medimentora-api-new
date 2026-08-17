"""Validation helpers for Body Systems Learning Hub APIs."""

from __future__ import annotations

from typing import Any

ALLOWED_DIFFICULTIES = {"beginner", "intermediate", "advanced", "easy", "medium", "hard"}
ALLOWED_PROGRESS_STATUS = {"not_started", "in_progress", "completed"}

# Kept in sync with HubAiTutorService.TUTOR_MODES
ALLOWED_TUTOR_MODES = {
  "explain_simply",
  "beginner",
  "nursing",
  "examples",
  "mnemonics",
  "english",
  "tamil",
  "practice_questions",
  "viva_questions",
  "flashcards",
  "exam_notes",
  "one_minute_summary",
  "five_minute_revision",
  "ask",
}


def validate_body_system_payload(payload: dict[str, Any] | None, *, partial: bool = False) -> list[str]:
  data = payload or {}
  errors: list[str] = []
  if not partial and not (data.get("name") or "").strip():
    errors.append("name is required.")
  if "difficulty" in data and data["difficulty"] is not None:
    diff = str(data["difficulty"]).strip().lower()
    if diff and diff not in ALLOWED_DIFFICULTIES:
      errors.append("difficulty must be beginner, intermediate, or advanced.")
  if "estimated_minutes" in data and data["estimated_minutes"] is not None:
    try:
      mins = int(data["estimated_minutes"])
      if mins < 0 or mins > 10080:
        errors.append("estimated_minutes must be between 0 and 10080.")
    except (TypeError, ValueError):
      errors.append("estimated_minutes must be an integer.")
  return errors


def validate_organ_payload(payload: dict[str, Any] | None, *, partial: bool = False) -> list[str]:
  data = payload or {}
  errors: list[str] = []
  if not partial and not (data.get("name") or "").strip():
    errors.append("name is required.")
  return errors


def validate_disease_payload(payload: dict[str, Any] | None, *, partial: bool = False) -> list[str]:
  data = payload or {}
  errors: list[str] = []
  if not partial and not (data.get("name") or "").strip():
    errors.append("name is required.")
  if "difficulty" in data and data["difficulty"] is not None:
    diff = str(data["difficulty"]).strip().lower()
    if diff and diff not in ALLOWED_DIFFICULTIES:
      errors.append("difficulty must be beginner, intermediate, or advanced.")
  return errors


def validate_progress_payload(payload: dict[str, Any] | None) -> list[str]:
  data = payload or {}
  errors: list[str] = []
  if "status" in data and data["status"] is not None:
    status = str(data["status"]).strip().lower()
    if status not in ALLOWED_PROGRESS_STATUS:
      errors.append("status must be not_started, in_progress, or completed.")
  if "progress_percent" in data and data["progress_percent"] is not None:
    try:
      pct = float(data["progress_percent"])
      if pct < 0 or pct > 100:
        errors.append("progress_percent must be between 0 and 100.")
    except (TypeError, ValueError):
      errors.append("progress_percent must be a number.")
  return errors


def validate_tutor_payload(payload: dict[str, Any] | None) -> list[str]:
  data = payload or {}
  errors: list[str] = []
  mode = str(data.get("mode") or "explain_simply").strip().lower()
  if mode not in ALLOWED_TUTOR_MODES:
    errors.append("mode is invalid.")
  organ = (data.get("organ_slug") or data.get("organ") or "").strip()
  system = (data.get("system_slug") or data.get("system") or data.get("body_system") or "").strip()
  if not organ and not system:
    errors.append("organ_slug or system_slug is required.")
  message = data.get("message")
  if message is not None and not isinstance(message, str):
    errors.append("message must be a string.")
  elif isinstance(message, str) and len(message) > 4000:
    errors.append("message must be at most 4000 characters.")
  return errors
