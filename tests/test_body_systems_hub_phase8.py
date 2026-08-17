"""Phase 8 — Hub flashcards tests."""

from __future__ import annotations

from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import HubFlashcard


def test_generate_list_and_favorite_flashcards(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  gen = client.post(
    "/api/learning/hub/flashcards/generate",
    json={"system_slug": "circulatory", "organ_slug": "heart", "force": True},
    headers=auth_headers,
  )
  assert gen.status_code in (200, 201), gen.get_data(as_text=True)
  data = gen.get_json()["data"]
  assert data["total"] >= 3
  levels = {c["card_level"] for c in data["items"]}
  assert "basic" in levels
  assert data["spaced_repetition"]["future_ready"] is True

  listed = client.get(
    "/api/learning/hub/flashcards",
    query_string={"system": "circulatory", "organ": "heart"},
    headers=auth_headers,
  )
  assert listed.status_code == 200
  items = listed.get_json()["data"]["items"]
  assert items
  card_id = items[0]["id"]

  fav = client.post(f"/api/learning/hub/flashcards/{card_id}/favorite", headers=auth_headers)
  assert fav.status_code == 200
  assert fav.get_json()["data"]["flashcard_id"] == card_id

  favs = client.get("/api/learning/hub/flashcards/favorites", headers=auth_headers)
  assert favs.status_code == 200
  assert favs.get_json()["data"]["total"] >= 1

  only_fav = client.get(
    "/api/learning/hub/flashcards",
    query_string={"system": "circulatory", "favorites": "true"},
    headers=auth_headers,
  )
  assert only_fav.status_code == 200
  assert all(i.get("is_favorite") for i in only_fav.get_json()["data"]["items"])

  unfav = client.delete(f"/api/learning/hub/flashcards/{card_id}/favorite", headers=auth_headers)
  assert unfav.status_code == 200


def test_flashcard_levels_cover_requirements(client, auth_headers, app_ctx):
  ensure_body_systems_hub_schema()
  gen = client.post(
    "/api/learning/hub/flashcards/generate",
    json={"system_slug": "respiratory", "organ_slug": "lungs", "force": True},
    headers=auth_headers,
  )
  assert gen.status_code in (200, 201)
  levels = {c.card_level for c in HubFlashcard.query.filter_by(body_system_id=gen.get_json()["data"]["body_system"]["id"]).all()}
  assert {"basic", "advanced", "exam_revision"} <= levels
