"""Phase 4 — Organ educational page content tests."""

from __future__ import annotations

from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import Organ
from app.services.body_systems.organ_content import CONTENT_VERSION


def test_phase4_organ_content_enriched(app_ctx):
  ensure_body_systems_hub_schema()
  heart = Organ.query.filter_by(slug="heart").first()
  assert heart is not None
  assert heart.animation_key == "heart_pumping"
  assert isinstance(heart.learning_objectives, list) and len(heart.learning_objectives) >= 1
  cj = heart.content_json or {}
  assert cj.get("version") == CONTENT_VERSION
  assert cj.get("overview")
  assert isinstance(cj.get("functions"), list) and len(cj["functions"]) >= 1
  assert isinstance(cj.get("common_diseases"), list)


def test_get_organ_returns_sections(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  detail = client.get(
    "/api/learning/organs/heart",
    query_string={"system": "circulatory"},
    headers=auth_headers,
  )
  assert detail.status_code == 200
  data = detail.get_json()["data"]
  assert data["slug"] == "heart"
  assert "sections" in data
  assert data["sections"]["overview"]
  assert isinstance(data["sections"]["functions"], list)
  assert data["safety"]["educational_only"] is True
  assert data["safety"]["not_a_diagnosis"] is True


def test_get_lungs_animation_key(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  detail = client.get("/api/learning/organs/lungs", headers=auth_headers)
  assert detail.status_code == 200
  data = detail.get_json()["data"]
  assert data["animation_key"] == "respiration"
  assert data["body_system"]["slug"] == "respiratory"
