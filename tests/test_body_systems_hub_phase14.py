"""Phase 14 — Admin Body Systems Hub management."""

from __future__ import annotations

import uuid

from app.extensions import db
from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import BodySystem, Organ
from app.services.body_systems.admin_service import AdminBodySystemService


def test_admin_list_and_create_body_system(client, admin_auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  suffix = uuid.uuid4().hex[:8]
  slug = f"phase14-test-{suffix}"

  listed = client.get(
    "/api/admin/learning/body-systems",
    query_string={"include_inactive": "true"},
    headers=admin_auth_headers,
  )
  assert listed.status_code == 200, listed.get_data(as_text=True)
  assert listed.get_json()["data"]["total"] >= 1

  created = client.post(
    "/api/admin/learning/body-systems",
    json={
      "name": f"Phase14 Test System {suffix}",
      "slug": slug,
      "short_description": "Admin panel test system",
      "difficulty": "beginner",
      "estimated_minutes": 90,
      "is_published": False,
    },
    headers=admin_auth_headers,
  )
  assert created.status_code == 201, created.get_data(as_text=True)
  body = created.get_json()["data"]
  assert body["slug"] == slug
  assert body["is_published"] is False

  updated = client.patch(
    f"/api/admin/learning/body-systems/{slug}",
    json={"is_published": True, "short_description": "Published via Phase 14"},
    headers=admin_auth_headers,
  )
  assert updated.status_code == 200, updated.get_data(as_text=True)
  assert updated.get_json()["data"]["is_published"] is True

  detail = client.get(
    f"/api/admin/learning/body-systems/{slug}",
    headers=admin_auth_headers,
  )
  assert detail.status_code == 200
  assert "organs" in detail.get_json()["data"]

  row = BodySystem.query.filter_by(slug=slug).first()
  if row:
    db.session.delete(row)
    db.session.commit()


def test_admin_get_includes_unpublished_organs(client, admin_auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  system = BodySystem.query.filter_by(slug="skeletal", is_active=True).first()
  assert system is not None

  organ_slug = f"phase14-draft-{uuid.uuid4().hex[:8]}"
  organ, code, _ = AdminBodySystemService.create_organ(
    "skeletal",
    {
      "name": "Phase14 Draft Organ",
      "slug": organ_slug,
      "is_published": False,
      "is_active": True,
    },
  )
  assert code is None
  assert organ is not None

  response = client.get(
    "/api/admin/learning/body-systems/skeletal",
    headers=admin_auth_headers,
  )
  assert response.status_code == 200
  organs = response.get_json()["data"]["organs"]
  assert any(o["slug"] == organ_slug for o in organs)

  row = Organ.query.filter_by(body_system_id=system.id, slug=organ_slug).first()
  if row:
    db.session.delete(row)
    db.session.commit()


def test_admin_body_systems_requires_admin(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  response = client.get("/api/admin/learning/body-systems", headers=auth_headers)
  assert response.status_code in (401, 403)
