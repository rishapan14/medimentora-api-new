"""Regression tests for student quiz and simulation submissions."""

from __future__ import annotations


def test_quiz_submission_survives_progress_tracking_failure(
  client, auth_headers, app_ctx, monkeypatch
):
  from app.extensions import db
  from app.models.quiz_model import Question, Quiz
  from app.services.learning_service import LearningService

  quiz = Quiz(title="Submission regression quiz", is_published=True)
  db.session.add(quiz)
  db.session.flush()
  question = Question(
    quiz_id=quiz.id,
    question_text="Normal adult resting heart rate?",
    options=["40-50 bpm", "60-100 bpm"],
    correct_answer="60-100 bpm",
  )
  db.session.add(question)
  db.session.commit()

  monkeypatch.setattr(
    LearningService,
    "record_quiz_score",
    lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("progress unavailable")),
  )

  response = client.post(
    f"/api/quizzes/{quiz.id}/submit",
    json={"answers": {str(question.id): "60-100 bpm"}, "time_taken_seconds": 12},
    headers=auth_headers,
  )

  assert response.status_code == 201
  result = response.get_json()["data"]["result"]
  assert result["score"] == 100
  assert result["time_taken_seconds"] == 12


def test_simulation_submission_falls_back_when_ai_and_progress_are_unavailable(
  client, auth_headers, app_ctx, monkeypatch
):
  from app.extensions import db
  from app.models.simulation_model import Simulation
  from app.services.ai_analysis_service import AIAnalysisService
  from app.services.learning_service import LearningService

  simulation = Simulation(
    title="Submission regression simulation",
    scenario="A patient presents with severe hyperglycemia.",
    correct_diagnosis="Hyperglycemic crisis",
    correct_treatment="IV fluids, insulin therapy, electrolyte monitoring",
    diagnosis_options=["Hypoglycemia", "Hyperglycemic crisis"],
    treatment_options=["Oral glucose", "IV fluids and insulin"],
    max_score=100,
    is_active=True,
  )
  db.session.add(simulation)
  db.session.commit()

  monkeypatch.setattr(
    AIAnalysisService,
    "simulation_feedback",
    lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
  )
  monkeypatch.setattr(
    LearningService,
    "record_simulation_score",
    lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("progress unavailable")),
  )

  response = client.post(
    f"/api/simulations/{simulation.id}/submit",
    json={
      "diagnosis_selected": "Hyperglycemic crisis",
      "treatment_selected": "IV fluids and insulin",
    },
    headers=auth_headers,
  )

  assert response.status_code == 201
  data = response.get_json()["data"]
  assert data["score"] == 100
  assert "fallback" in data["feedback"].lower()
