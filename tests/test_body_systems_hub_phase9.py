"""Phase 9 — Hub clinical cases + disease explorer tests."""

from __future__ import annotations

from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import HubDisease, HubDiseaseClinicalCase
from app.models.clinical_case_model import ClinicalCase


def test_generate_and_list_hub_cases(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  gen = client.post(
    "/api/learning/body-systems/circulatory/cases/generate",
    json={"organ_slug": "heart", "force": True},
    headers=auth_headers,
  )
  assert gen.status_code in (200, 201), gen.get_data(as_text=True)
  data = gen.get_json()["data"]
  assert data["total"] >= 1
  assert data["diseases"]
  case = data["items"][0]["clinical_case"]
  assert case["content_json"]
  assert case["sections"]["patient"]
  assert case["sections"]["learning_points"]
  assert "patient" in data["walkthrough_steps"]
  assert data["safety"]["educational_only"] is True

  listed = client.get(
    "/api/learning/body-systems/circulatory/cases",
    query_string={"organ": "heart"},
    headers=auth_headers,
  )
  assert listed.status_code == 200
  assert listed.get_json()["data"]["total"] >= 1


def test_disease_includes_cases_and_explorer(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  client.post(
    "/api/learning/body-systems/respiratory/cases/generate",
    json={"organ_slug": "lungs", "force": True},
    headers=auth_headers,
  )
  disease = HubDisease.query.filter(HubDisease.name.ilike("%pneumonia%")).first()
  assert disease is not None
  detail = client.get(
    f"/api/learning/diseases/{disease.slug}",
    query_string={"system": "respiratory"},
    headers=auth_headers,
  )
  assert detail.status_code == 200
  data = detail.get_json()["data"]
  assert "explorer" in data
  assert isinstance(data.get("clinical_cases"), list)
  assert HubDiseaseClinicalCase.query.filter_by(disease_id=disease.id).count() >= 1
  assert ClinicalCase.query.filter(ClinicalCase.title.like("[Hub]%")).count() >= 1
