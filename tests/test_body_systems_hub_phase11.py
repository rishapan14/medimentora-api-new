"""Phase 11 — X-ray analysis → Body Systems Hub recommendations."""

from __future__ import annotations

from app.extensions import db
from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import HubRecommendation
from app.models.user_model import User
from app.models.xray_analysis_model import XrayAnalysis
from app.services.body_systems.hub_xray_recommendation_service import (
  HubXrayRecommendationService,
)


def _auth_user():
  return User.query.filter_by(email="student@clinical.com").first() or User.query.first()


def test_xray_finding_maps_to_respiratory_hub(app_ctx):
  ensure_body_systems_hub_schema()
  user = _auth_user()
  assert user is not None
  analysis = XrayAnalysis(
    user_id=user.id,
    filename="demo-chest.png",
    file_path="/tmp/demo-chest.png",
    body_part="Chest",
    possible_findings=[
      {
        "label": "Pneumonia (possible educational pattern)",
        "probability": 0.72,
        "region": "right lower lobe",
        "rationale": "Opacity themes for learning",
      }
    ],
    status="completed",
  )
  db.session.add(analysis)
  db.session.commit()

  recs = HubXrayRecommendationService.recommend_for_analysis(analysis, user_id=user.id)
  assert len(recs) >= 1
  assert recs[0]["source_type"] == "xray"
  assert "/learning/body-systems/respiratory" in (recs[0]["href"] or "")
  meta = recs[0].get("meta_json") or {}
  links = meta.get("links") or {}
  assert "explorer_3d" in links
  assert "from=xray" in (links["explorer_3d"] or "")
  assert "part=lungs" in (links["explorer_3d"] or "")
  assert HubRecommendation.query.filter_by(source_type="xray", source_id=analysis.id).count() >= 1

  payload = analysis.to_dict()
  assert isinstance(payload.get("hub_recommendations"), list)
  assert len(payload["hub_recommendations"]) >= 1


def test_hub_recommendations_filter_by_xray_source(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  user = _auth_user()
  assert user is not None
  analysis = XrayAnalysis(
    user_id=user.id,
    filename="demo-fracture.png",
    file_path="/tmp/demo-fracture.png",
    body_part="Wrist",
    possible_findings=[{"label": "Possible fracture pattern", "probability": 0.6}],
    status="completed",
  )
  db.session.add(analysis)
  db.session.commit()

  HubXrayRecommendationService.recommend_for_analysis(analysis, user_id=user.id)

  response = client.get(
    "/api/learning/hub/recommendations",
    query_string={"source_type": "xray", "source_id": analysis.id},
    headers=auth_headers,
  )
  assert response.status_code == 200, response.get_data(as_text=True)
  data = response.get_json()["data"]
  assert data["total"] >= 1
  assert all(i["source_type"] == "xray" for i in data["items"])
  assert data["safety"]["educational_only"] is True
  assert any("/learning/body-systems/skeletal" in (i.get("href") or "") for i in data["items"])
