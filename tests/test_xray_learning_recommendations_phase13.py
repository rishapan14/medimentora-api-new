"""Phase 13 — learning recommendations from X-ray analysis."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.xray.recommendation_service import (
  RECOMMENDATION_VERSION,
  XrayRecommendationService,
)


def test_resolve_findings_prefers_possible():
  row = SimpleNamespace(
    possible_findings=[{"label": "Possible Pneumonia", "probability": 0.7}],
    structured_findings={"findings": [{"label": "Possible Fracture", "probability": 0.5}]},
  )
  resolved = XrayRecommendationService.resolve_findings(row)
  assert resolved[0]["label"] == "Possible Pneumonia"


def test_resolve_findings_falls_back_to_structured():
  row = SimpleNamespace(
    possible_findings=[],
    structured_findings={
      "findings": [{"label": "Possible Fracture", "probability": 0.55}],
    },
  )
  resolved = XrayRecommendationService.resolve_findings(row)
  assert resolved[0]["label"] == "Possible Fracture"


def test_pneumothorax_and_consolidation_topics(app_ctx):
  result = XrayRecommendationService.build_recommendations(
    possible_findings=[
      {"label": "Possible Pneumothorax", "probability": 0.6},
      {"label": "Possible Consolidation", "probability": 0.5},
    ],
    body_part="Chest",
    sync_user_recommendations=False,
  )
  assert result.success
  blob = " ".join(result.topics).lower()
  assert "chest" in blob or "respiratory" in blob or "pneumonia" in blob
  assert any(r.get("href") for r in result.recommendations)


def test_lesson_href_includes_lesson_query(app_ctx):
  result = XrayRecommendationService.build_recommendations(
    possible_findings=[{"label": "Possible Fracture", "probability": 0.7}],
    body_part="Hand",
    sync_user_recommendations=False,
  )
  assert result.success
  lessons = [r for r in result.recommendations if r.get("type") == "lesson" and r.get("lesson_id")]
  for lesson in lessons:
    assert f"lesson={lesson['lesson_id']}" in str(lesson.get("href") or "")


def test_recommendation_version_phase13(app_ctx):
  result = XrayRecommendationService.build_recommendations(
    possible_findings=[{"label": "Possible Cardiomegaly", "probability": 0.6}],
    body_part="Chest",
    sync_user_recommendations=False,
  )
  assert result.success
  assert result.to_dict()["recommendation_version"] == RECOMMENDATION_VERSION
  assert RECOMMENDATION_VERSION.startswith("1.3")
