"""Module 8 — Admin Quiz Management API tests."""

from __future__ import annotations


def test_admin_quizzes_requires_admin(client, auth_headers):
  resp = client.get("/api/admin/quizzes", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_list_quizzes_ok(client, admin_auth_headers):
  resp = client.get("/api/admin/quizzes?limit=20", headers=admin_auth_headers)
  assert resp.status_code == 200
  data = resp.get_json()["data"]
  assert "quizzes" in data
  assert "stats" in data
  assert "quizzes" in data["stats"]


def test_admin_quiz_and_question_crud(client, admin_auth_headers, app_ctx):
  from app.extensions import db
  from app.models.quiz_model import Question, Quiz

  create = client.post(
    "/api/admin/quizzes",
    json={
      "title": "Admin Module 8 Test Quiz",
      "description": "Educational quiz for Module 8 tests.",
      "difficulty": "medium",
      "speciality": "Nursing",
      "time_limit_minutes": 20,
      "passing_score": 70,
      "is_published": False,
    },
    headers=admin_auth_headers,
  )
  assert create.status_code == 201
  quiz = create.get_json()["data"]["quiz"]
  quiz_id = quiz["id"]
  assert quiz["is_published"] is False

  publish = client.post(
    f"/api/admin/quizzes/{quiz_id}/publish",
    json={"is_published": True},
    headers=admin_auth_headers,
  )
  assert publish.status_code == 200
  assert publish.get_json()["data"]["quiz"]["is_published"] is True

  question = client.post(
    f"/api/admin/quizzes/{quiz_id}/questions",
    json={
      "question_text": "What is the normal adult resting heart rate range?",
      "options": ["40-50 bpm", "60-100 bpm", "120-150 bpm", "20-30 bpm"],
      "correct_answer": "60-100 bpm",
      "explanation": "Typical resting heart rate for adults is about 60–100 bpm.",
      "points": 1,
    },
    headers=admin_auth_headers,
  )
  assert question.status_code == 201
  question_id = question.get_json()["data"]["question"]["id"]
  assert question.get_json()["data"]["question"]["correct_answer"] == "60-100 bpm"

  listed = client.get(
    f"/api/admin/quizzes/{quiz_id}/questions",
    headers=admin_auth_headers,
  )
  assert listed.status_code == 200
  ids = [q["id"] for q in listed.get_json()["data"]["questions"]]
  assert question_id in ids

  bad = client.post(
    f"/api/admin/quizzes/{quiz_id}/questions",
    json={
      "question_text": "Bad question",
      "options": ["A", "B"],
      "correct_answer": "C",
    },
    headers=admin_auth_headers,
  )
  assert bad.status_code == 400

  deleted_q = client.delete(
    f"/api/admin/quizzes/questions/{question_id}",
    headers=admin_auth_headers,
  )
  assert deleted_q.status_code == 200
  assert db.session.get(Question, question_id) is None

  deleted = client.delete(
    f"/api/admin/quizzes/{quiz_id}",
    headers=admin_auth_headers,
  )
  assert deleted.status_code == 200
  assert db.session.get(Quiz, quiz_id) is None


def test_admin_create_quiz_validation(client, admin_auth_headers):
  resp = client.post(
    "/api/admin/quizzes",
    json={"description": "missing title"},
    headers=admin_auth_headers,
  )
  assert resp.status_code == 400
