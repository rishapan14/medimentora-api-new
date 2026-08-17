"""Phase 5 — Interactive Human Body Explorer API tests."""

from __future__ import annotations

from app.helpers.schema_patches import ensure_body_systems_hub_schema


def test_hub_explorer_catalog(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  response = client.get("/api/learning/hub/explorer", headers=auth_headers)
  assert response.status_code == 200, response.get_data(as_text=True)
  data = response.get_json()["data"]
  assert data["renderer"] == "svg-2d"
  assert "gltf-3d" in data["supported_renderers"]
  assert data["capabilities"]["zoom"] is True
  assert data["capabilities"]["rotate_future_ready"] is True
  assert data["total"] >= 10
  slugs = {item["slug"] for item in data["items"]}
  assert {"heart", "lungs", "brain", "kidneys", "bones", "muscles"} <= slugs
  heart = next(i for i in data["items"] if i["slug"] == "heart")
  assert heart["region_key"] == "heart"
  assert heart["href"].endswith("/organs/heart")
  assert heart["body_system"]["slug"] == "circulatory"
  assert data["safety"]["educational_only"] is True
