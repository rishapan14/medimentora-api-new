"""Phase 10 — Report analysis → Body Systems Hub recommendations."""

from __future__ import annotations

from app.extensions import db
from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import HubRecommendation
from app.models.report_analysis_model import ReportAnalysis
from app.models.user_model import User
from app.services.body_systems.hub_report_recommendation_service import (
  HubReportRecommendationService,
)


def _auth_user():
  return User.query.filter_by(email="student@clinical.com").first() or User.query.first()


def test_report_finding_maps_to_circulatory_hub(app_ctx):
  ensure_body_systems_hub_schema()
  user = _auth_user()
  assert user is not None
  analysis = ReportAnalysis(
    user_id=user.id,
    report_text="CBC shows low Hemoglobin 8.5 g/dL",
    simple_explanation="Educational explanation of low hemoglobin themes.",
    abnormal_values=[
      {
        "name": "Hemoglobin",
        "value": "8.5",
        "normal_range": "12-16",
        "status": "low",
        "significance": "May be discussed with anemia learning themes",
      }
    ],
    possible_diseases=[
      {
        "disease": "Anemia (possible)",
        "likelihood": "medium",
        "reasoning": "Low hemoglobin educational pattern",
      }
    ],
    learning_topics=["Hemoglobin", "Anemia", "Iron metabolism"],
  )
  db.session.add(analysis)
  db.session.commit()

  recs = HubReportRecommendationService.recommend_for_analysis(analysis, user_id=user.id)
  assert len(recs) >= 1
  assert recs[0]["source_type"] == "report"
  assert "/learning/body-systems/circulatory" in (recs[0]["href"] or "")
  meta = recs[0].get("meta_json") or {}
  links = meta.get("links") or {}
  assert "explorer_3d" in links
  assert "from=report" in (links["explorer_3d"] or "")
  assert HubRecommendation.query.filter_by(source_type="report", source_id=analysis.id).count() >= 1


def test_hub_recommendations_filter_by_source(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  user = _auth_user()
  assert user is not None
  analysis = ReportAnalysis(
    user_id=user.id,
    abnormal_values=[{"name": "Creatinine", "status": "high", "significance": "kidney"}],
    possible_diseases=[],
    learning_topics=["Kidney"],
  )
  db.session.add(analysis)
  db.session.commit()

  HubReportRecommendationService.recommend_for_analysis(analysis, user_id=user.id)

  response = client.get(
    "/api/learning/hub/recommendations",
    query_string={"source_type": "report", "source_id": analysis.id},
    headers=auth_headers,
  )
  assert response.status_code == 200, response.get_data(as_text=True)
  data = response.get_json()["data"]
  assert data["total"] >= 1
  assert all(i["source_type"] == "report" for i in data["items"])
  assert data["safety"]["educational_only"] is True
