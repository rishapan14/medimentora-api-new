"""Phase 2 — Body Systems Learning Hub API tests."""

from __future__ import annotations

import uuid

from app.extensions import db
from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import HubDisease, Organ


def test_list_body_systems_requires_auth(client, app_ctx):
  ensure_body_systems_hub_schema()
  response = client.get("/api/learning/body-systems")
  assert response.status_code in (401, 422)


def test_list_body_systems_ok(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  response = client.get("/api/learning/body-systems", headers=auth_headers)
  assert response.status_code == 200, response.get_data(as_text=True)
  body = response.get_json()
  assert body["status"] == "success"
  items = body["data"]["items"]
  assert len(items) >= 11
  slugs = {i["slug"] for i in items}
  assert "circulatory" in slugs
  assert "respiratory" in slugs
  assert items[0]["safety"]["educational_only"] is True
  assert "progress" in items[0]


def test_get_body_system_detail(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  response = client.get("/api/learning/body-systems/circulatory", headers=auth_headers)
  assert response.status_code == 200
  data = response.get_json()["data"]
  assert data["slug"] == "circulatory"
  assert isinstance(data["organs"], list)
  assert any(o["slug"] == "heart" for o in data["organs"])
  assert data["safety"]["not_a_diagnosis"] is True


def test_list_organs_and_get_organ(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  listed = client.get("/api/learning/body-systems/circulatory/organs", headers=auth_headers)
  assert listed.status_code == 200
  assert listed.get_json()["data"]["total"] >= 1

  detail = client.get("/api/learning/organs/heart", headers=auth_headers)
  assert detail.status_code == 200
  assert detail.get_json()["data"]["slug"] == "heart"
  assert detail.get_json()["data"]["body_system"]["slug"] == "circulatory"


def test_hub_search(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  response = client.get("/api/learning/hub/search", query_string={"q": "heart"}, headers=auth_headers)
  assert response.status_code == 200
  data = response.get_json()["data"]
  assert data["total"] >= 1
  assert any(o["slug"] == "heart" for o in data["organs"]) or any(
    s["slug"] == "circulatory" for s in data["systems"]
  )


def test_start_and_update_progress(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  started = client.post("/api/learning/body-systems/respiratory/start", headers=auth_headers)
  assert started.status_code == 200
  progress = started.get_json()["data"]["progress"]
  assert progress["status"] == "in_progress"

  updated = client.put(
    "/api/learning/body-systems/respiratory/progress",
    json={"status": "in_progress", "progress_percent": 35},
    headers=auth_headers,
  )
  assert updated.status_code == 200
  assert updated.get_json()["data"]["progress"]["progress_percent"] == 35


def test_admin_create_organ(client, admin_auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  suffix = uuid.uuid4().hex[:8]
  slug = f"spinal-cord-{suffix}"
  response = client.post(
    "/api/admin/learning/body-systems/nervous/organs",
    json={
      "name": f"Spinal Cord {suffix}",
      "slug": slug,
      "short_description": "Educational overview of the spinal cord.",
      "location": "spine",
    },
    headers=admin_auth_headers,
  )
  assert response.status_code in (200, 201), response.get_data(as_text=True)
  data = response.get_json()["data"]
  assert data["slug"] == slug

  again = client.post(
    "/api/admin/learning/body-systems/nervous/organs",
    json={"name": f"Spinal Cord {suffix}", "slug": slug},
    headers=admin_auth_headers,
  )
  assert again.status_code == 409

  row = Organ.query.filter_by(slug=slug).first()
  if row:
    db.session.delete(row)
    db.session.commit()


def test_admin_create_disease(client, admin_auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  suffix = uuid.uuid4().hex[:8]
  slug = f"pneumonia-{suffix}"
  response = client.post(
    "/api/admin/learning/body-systems/respiratory/diseases",
    json={
      "name": f"Pneumonia Educational {suffix}",
      "slug": slug,
      "organ_slug": "lungs",
      "short_description": "Educational overview of pneumonia patterns for learners.",
      "content_json": {
        "safety": {"educational_only": True, "not_a_diagnosis": True},
        "signs": [],
        "symptoms": [],
      },
    },
    headers=admin_auth_headers,
  )
  assert response.status_code in (200, 201), response.get_data(as_text=True)
  assert response.get_json()["data"]["slug"] == slug

  student_get = client.get(
    f"/api/learning/diseases/{slug}?system=respiratory",
    headers=admin_auth_headers,
  )
  assert student_get.status_code == 200

  row = HubDisease.query.filter_by(slug=slug).first()
  if row:
    db.session.delete(row)
    db.session.commit()
