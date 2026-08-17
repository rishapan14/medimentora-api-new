"""Phase 12 — Body Systems Hub progress tracking."""

from __future__ import annotations

from app.extensions import db
from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import BodySystem, BodySystemProgress, Organ
from app.models.user_model import User
from app.services.body_systems.hub_service import BodySystemHubService


def _auth_user():
  return User.query.filter_by(email="student@clinical.com").first() or User.query.first()


def test_organ_view_bumps_progress(app_ctx):
  ensure_body_systems_hub_schema()
  user = _auth_user()
  assert user is not None
  system = BodySystem.query.filter_by(slug="respiratory", is_active=True).first()
  assert system is not None
  organ = Organ.query.filter_by(body_system_id=system.id, is_active=True).first()
  assert organ is not None

  BodySystemProgress.query.filter_by(user_id=user.id, body_system_id=system.id).delete()
  db.session.commit()

  payload = BodySystemHubService.get_organ(organ.slug, system_slug=system.slug, user_id=user.id)
  assert payload is not None
  assert payload.get("progress") is not None
  assert payload["progress"]["status"] == "in_progress"
  assert float(payload["progress"]["progress_percent"]) >= 4.0
  assert payload["progress"]["last_organ_id"] == organ.id

  # Refresh same organ — no additional bump
  pct = float(payload["progress"]["progress_percent"])
  payload2 = BodySystemHubService.get_organ(organ.slug, system_slug=system.slug, user_id=user.id)
  assert float(payload2["progress"]["progress_percent"]) == pct


def test_hub_progress_summary_endpoint(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  user = _auth_user()
  assert user is not None
  system = BodySystem.query.filter_by(slug="circulatory", is_active=True).first()
  assert system is not None

  BodySystemHubService.get_or_start_progress(user.id, system.slug)
  BodySystemHubService.update_progress(
    user.id,
    system.slug,
    {"status": "in_progress", "progress_percent": 40, "study_minutes": 12},
  )

  response = client.get("/api/learning/hub/progress", headers=auth_headers)
  assert response.status_code == 200, response.get_data(as_text=True)
  data = response.get_json()["data"]
  assert "summary" in data
  assert data["summary"]["total_systems"] >= 1
  assert data["summary"]["overall_percent"] >= 0
  assert isinstance(data["systems"], list)
  assert len(data["systems"]) >= 1
  assert data["safety"]["educational_only"] is True
  assert any(s["slug"] == "circulatory" for s in data["systems"])
