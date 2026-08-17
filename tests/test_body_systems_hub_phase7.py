"""Phase 7 — Body Systems Hub Quiz tests."""

from __future__ import annotations

from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.quiz_model import Question


def test_generate_and_list_hub_quiz(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  gen = client.post(
    "/api/learning/body-systems/circulatory/quizzes/generate",
    json={"difficulty": "intermediate"},
    headers=auth_headers,
  )
  assert gen.status_code in (200, 201), gen.get_data(as_text=True)
  data = gen.get_json()["data"]
  assert data["quiz"]["id"]
  assert data["quiz"]["question_count"] >= 3
  assert data["safety"]["educational_only"] is True

  listed = client.get("/api/learning/body-systems/circulatory/quizzes", headers=auth_headers)
  assert listed.status_code == 200
  items = listed.get_json()["data"]["items"]
  assert len(items) >= 1
  assert "multiple_choice" in listed.get_json()["data"]["supported_question_types"]
  assert listed.get_json()["data"]["drag_drop"]["available"] is False


def test_generate_organ_quiz_has_mixed_types(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  gen = client.post(
    "/api/learning/body-systems/circulatory/quizzes/generate",
    json={"organ_slug": "heart", "force": True},
    headers=auth_headers,
  )
  assert gen.status_code in (200, 201), gen.get_data(as_text=True)
  quiz_id = gen.get_json()["data"]["quiz"]["id"]
  types = {q.question_type for q in Question.query.filter_by(quiz_id=quiz_id).all()}
  assert "multiple_choice" in types
  assert "true_false" in types
  assert "fill_in_blank" in types or "case_based" in types


def test_hub_quiz_submit_scores(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  gen = client.post(
    "/api/learning/body-systems/respiratory/quizzes/generate",
    json={"organ_slug": "lungs", "force": True},
    headers=auth_headers,
  )
  assert gen.status_code in (200, 201)
  quiz = gen.get_json()["data"]["quiz"]
  quiz_id = quiz["id"]

  detail = client.get(f"/api/quizzes/{quiz_id}", headers=auth_headers)
  assert detail.status_code == 200
  questions = detail.get_json()["data"]["quiz"]["questions"]
  assert questions

  # Build answers from DB (include_answer not in student get — use Question model)
  answers = {}
  for q in Question.query.filter_by(quiz_id=quiz_id).all():
    answers[str(q.id)] = q.correct_answer

  submitted = client.post(
    f"/api/quizzes/{quiz_id}/submit",
    json={"answers": answers},
    headers=auth_headers,
  )
  assert submitted.status_code in (200, 201), submitted.get_data(as_text=True)
  result = submitted.get_json()["data"]["result"]
  assert float(result["score"]) == 100.0
