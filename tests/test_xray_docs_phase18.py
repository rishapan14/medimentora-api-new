"""Phase 18 — X-ray OpenAPI / Swagger smoke tests."""

from __future__ import annotations


def test_openapi_yaml_served(client):
  response = client.get("/apispec/xray.yaml")
  assert response.status_code == 200, response.get_data(as_text=True)
  body = response.get_data(as_text=True)
  assert "openapi:" in body
  assert "/api/xray/upload" in body
  assert "/api/admin/xray-analyses/evaluation-metrics" in body
  assert "educational" in body.lower()
  assert "not a diagnosis" in body.lower() or "not a clinical" in body.lower()


def test_openapi_meta_json(client):
  response = client.get("/apispec/xray")
  assert response.status_code == 200
  payload = response.get_json()
  assert payload["status"] == "success"
  data = payload["data"]
  assert data["spec_url"] == "/apispec/xray.yaml"
  assert data["swagger_ui"] == "/apidocs"
  assert data["scope"] == "xray_only"
  assert data["spec_present"] is True
  assert "educational" in (data.get("disclaimer") or "").lower()
  safety = data.get("evaluation_safety") or {}
  assert safety.get("educational_monitoring_only") is True
  assert safety.get("not_clinical_performance") is True


def test_swagger_ui_html(client):
  response = client.get("/apidocs")
  assert response.status_code == 200
  html = response.get_data(as_text=True)
  assert "swagger-ui" in html.lower()
  assert "/apispec/xray.yaml" in html
  assert "Educational only" in html


def test_home_exposes_docs_links(client):
  response = client.get("/")
  assert response.status_code == 200
  docs = (response.get_json().get("data") or {}).get("docs") or {}
  assert docs.get("xray_swagger_ui") == "/apidocs"
  assert docs.get("xray_openapi") == "/apispec/xray.yaml"
