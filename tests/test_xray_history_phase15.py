"""Phase 15 — X-ray history pagination, date filters, and card fields."""

from __future__ import annotations

from app.models.xray_analysis_model import XrayAnalysis


def test_history_card_has_heatmap_flag():
  row = XrayAnalysis(
    user_id=1,
    filename="demo.png",
    file_path="/tmp/demo.png",
    heatmap_path="/tmp/demo_heatmap.png",
  )
  card = row.to_history_card()
  assert card["has_heatmap"] is True
  assert card["heatmap_path"]

  row2 = XrayAnalysis(
    user_id=1,
    filename="demo2.png",
    file_path="/tmp/demo2.png",
    heatmap_path=None,
  )
  card2 = row2.to_history_card()
  assert card2["has_heatmap"] is False


def test_history_api_pagination_contract(client, auth_headers):
  response = client.get("/api/xray/history?limit=5&page=1", headers=auth_headers)
  assert response.status_code == 200
  body = response.get_json()
  payload = body.get("data") if isinstance(body.get("data"), dict) else body
  assert "history" in payload
  assert "total" in payload
  assert payload["limit"] == 5
  assert payload["offset"] == 0
  assert "has_more" in payload
  assert "filters_applied" in payload
  assert payload["filters_applied"].get("limit") == 5


def test_history_api_date_filters_echo(client, auth_headers):
  response = client.get(
    "/api/xray/history?date_from=2026-01-01&date_to=2026-12-31&limit=10",
    headers=auth_headers,
  )
  assert response.status_code == 200
  body = response.get_json()
  payload = body.get("data") if isinstance(body.get("data"), dict) else body
  applied = payload.get("filters_applied") or {}
  assert applied.get("date_from") == "2026-01-01"
  assert applied.get("date_to") == "2026-12-31"
  assert isinstance(payload.get("history"), list)


def test_history_api_invalid_date(client, auth_headers):
  response = client.get(
    "/api/xray/history?date_from=not-a-date",
    headers=auth_headers,
  )
  assert response.status_code == 400
