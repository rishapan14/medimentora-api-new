"""Phase 6 — Hub AI Tutor tests (offline fallback path)."""

from __future__ import annotations

from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.services.body_systems.tutor_service import HubAiTutorService, TUTOR_MODES


def test_tutor_modes_endpoint(client, auth_headers, app_ctx):
  response = client.get("/api/learning/hub/tutor/modes", headers=auth_headers)
  assert response.status_code == 200
  modes = response.get_json()["data"]["modes"]
  ids = {m["id"] for m in modes}
  assert "explain_simply" in ids
  assert "tamil" in ids
  assert "flashcards" in ids


def test_tutor_requires_context(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  response = client.post(
    "/api/learning/hub/tutor",
    json={"mode": "explain_simply"},
    headers=auth_headers,
  )
  assert response.status_code == 400


def test_tutor_organ_offline_fallback(client, auth_headers, app_ctx, monkeypatch):
  ensure_body_systems_hub_schema()

  def _no_ai(system_prompt, user_prompt):
    return None, "none"

  monkeypatch.setattr(
    "app.services.body_systems.tutor_service.TeacherAIClient.complete_json",
    _no_ai,
  )

  response = client.post(
    "/api/learning/hub/tutor",
    json={
      "mode": "explain_simply",
      "organ_slug": "heart",
      "system_slug": "circulatory",
    },
    headers=auth_headers,
  )
  assert response.status_code == 200, response.get_data(as_text=True)
  data = response.get_json()["data"]
  assert data["used_fallback"] is True
  assert data["provider"] == "offline"
  assert data["answer"]
  assert data["safety"]["educational_only"] is True
  assert data["safety"]["not_a_diagnosis"] is True
  assert data["context"]["organ_slug"] == "heart"


def test_tutor_flashcards_mode(client, auth_headers, app_ctx, monkeypatch):
  ensure_body_systems_hub_schema()
  monkeypatch.setattr(
    "app.services.body_systems.tutor_service.TeacherAIClient.complete_json",
    lambda *_a, **_k: (None, "none"),
  )
  response = client.post(
    "/api/learning/hub/tutor",
    json={"mode": "flashcards", "organ_slug": "lungs"},
    headers=auth_headers,
  )
  assert response.status_code == 200
  data = response.get_json()["data"]
  assert isinstance(data["flashcards"], list)
  assert len(data["flashcards"]) >= 1


def test_tutor_service_modes_cover_requirements():
  required = {
    "explain_simply",
    "beginner",
    "nursing",
    "examples",
    "mnemonics",
    "tamil",
    "english",
    "practice_questions",
    "viva_questions",
    "flashcards",
    "exam_notes",
  }
  assert required <= set(TUTOR_MODES)
  assert len(HubAiTutorService.list_modes()) == len(TUTOR_MODES)


def test_tutor_3d_source_and_viva_offline(client, auth_headers, app_ctx, monkeypatch):
  ensure_body_systems_hub_schema()
  monkeypatch.setattr(
    "app.services.body_systems.tutor_service.TeacherAIClient.complete_json",
    lambda *_a, **_k: (None, "none"),
  )
  response = client.post(
    "/api/learning/hub/tutor",
    json={
      "mode": "viva_questions",
      "organ_slug": "heart",
      "source": "anatomy_3d",
    },
    headers=auth_headers,
  )
  assert response.status_code == 200
  data = response.get_json()["data"]
  assert data["used_fallback"] is True
  assert isinstance(data["questions"], list)
  assert len(data["questions"]) >= 1
  assert data["mode"] == "viva_questions"
