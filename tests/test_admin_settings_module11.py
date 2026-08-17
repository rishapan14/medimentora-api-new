"""Module 11 — Admin Settings API tests."""

from __future__ import annotations


def test_admin_settings_requires_admin(client, auth_headers):
  resp = client.get("/api/admin/settings", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_get_settings_ok(client, admin_auth_headers):
  resp = client.get("/api/admin/settings", headers=admin_auth_headers)
  assert resp.status_code == 200
  data = resp.get_json()["data"]
  assert "settings" in data
  assert "system" in data
  assert data["settings"]["platform_name"]
  assert "ai_report_analysis_enabled" in data["settings"]


def test_admin_update_and_reset_settings(client, admin_auth_headers, app_ctx):
  from app.extensions import db
  from app.models.platform_setting_model import PlatformSetting

  update = client.patch(
    "/api/admin/settings",
    json={
      "platform_name": "MediMentora Admin Test",
      "maintenance_mode": True,
      "default_quiz_passing_score": 80,
    },
    headers=admin_auth_headers,
  )
  assert update.status_code == 200
  settings = update.get_json()["data"]["settings"]
  assert settings["platform_name"] == "MediMentora Admin Test"
  assert settings["maintenance_mode"] is True
  assert settings["default_quiz_passing_score"] == 80

  row = db.session.get(PlatformSetting, "platform_name")
  assert row is not None
  assert row.value == "MediMentora Admin Test"

  reset = client.post("/api/admin/settings/reset", headers=admin_auth_headers)
  assert reset.status_code == 200
  restored = reset.get_json()["data"]["settings"]
  assert restored["platform_name"] == "MediMentora"
  assert restored["maintenance_mode"] is False
  assert restored["default_quiz_passing_score"] == 70


def test_admin_settings_validation(client, admin_auth_headers):
  resp = client.patch(
    "/api/admin/settings",
    json={"default_quiz_passing_score": 250},
    headers=admin_auth_headers,
  )
  assert resp.status_code == 400

  unknown = client.patch(
    "/api/admin/settings",
    json={"not_a_real_key": True},
    headers=admin_auth_headers,
  )
  assert unknown.status_code == 400
