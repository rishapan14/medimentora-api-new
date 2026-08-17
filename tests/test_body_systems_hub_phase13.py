"""Phase 13 — Body Systems Hub educational certificates."""

from __future__ import annotations

from app.extensions import db
from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import BodySystem, HubCertificate
from app.models.user_model import User
from app.services.body_systems.hub_certificate_service import HubCertificateService
from app.services.body_systems.hub_service import BodySystemHubService


def _auth_user():
  return User.query.filter_by(email="student@clinical.com").first() or User.query.first()


def test_completing_system_issues_hub_certificate(app_ctx):
  ensure_body_systems_hub_schema()
  user = _auth_user()
  assert user is not None
  system = BodySystem.query.filter_by(slug="nervous", is_active=True).first()
  assert system is not None

  HubCertificate.query.filter_by(user_id=user.id, body_system_id=system.id).delete()
  db.session.commit()

  payload, err = BodySystemHubService.update_progress(
    user.id,
    system.slug,
    {"status": "completed", "progress_percent": 100, "study_minutes": 45},
  )
  assert err is None
  assert payload["progress"]["status"] == "completed"

  certs = HubCertificate.query.filter_by(user_id=user.id, body_system_id=system.id).all()
  assert len(certs) == 1
  assert certs[0].certificate_number.startswith("HUB-")

  # Idempotent — second completion does not duplicate
  BodySystemHubService.update_progress(
    user.id, system.slug, {"status": "completed", "progress_percent": 100}
  )
  assert HubCertificate.query.filter_by(user_id=user.id, body_system_id=system.id).count() == 1


def test_list_hub_certificates_endpoint(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  user = _auth_user()
  assert user is not None
  system = BodySystem.query.filter_by(slug="digestive", is_active=True).first()
  assert system is not None

  BodySystemHubService.update_progress(
    user.id, system.slug, {"status": "completed", "progress_percent": 100}
  )

  response = client.get("/api/learning/hub/certificates", headers=auth_headers)
  assert response.status_code == 200, response.get_data(as_text=True)
  data = response.get_json()["data"]
  assert data["total"] >= 1
  assert data["safety"]["educational_only"] is True
  assert data["safety"]["not_a_license"] is True
  assert any(i.get("body_system_id") == system.id for i in data["items"])
  issued = next(i for i in data["items"] if i.get("body_system_id") == system.id)
  links = (issued.get("meta_json") or {}).get("links") or {}
  # Newly issued certs include 3D explorer deep-link (Phase 12)
  if links:
    assert "explorer_3d" in links
    assert "from=certificate" in (links.get("explorer_3d") or "")
