"""Settings feature-flag enforcement tests (post Module 11)."""

from __future__ import annotations


def test_platform_status_public(client):
  resp = client.get("/api/platform/status")
  assert resp.status_code == 200
  data = resp.get_json()["data"]
  assert "maintenance_mode" in data
  assert "allow_registrations" in data
  assert "ai_report_analysis_enabled" in data
  assert "ai_xray_analysis_enabled" in data


def test_registrations_closed_blocks_register(client, admin_auth_headers, app_ctx):
  closed = client.patch(
    "/api/admin/settings",
    json={"allow_registrations": False},
    headers=admin_auth_headers,
  )
  assert closed.status_code == 200

  resp = client.post(
    "/api/auth/register",
    json={
      "full_name": "Blocked User",
      "email": "blocked_register_test@example.com",
      "password": "secret123",
      "role": "medical_student",
    },
  )
  assert resp.status_code == 403
  assert resp.get_json().get("data", {}).get("error_code") == "registrations_closed"

  # restore
  client.patch(
    "/api/admin/settings",
    json={"allow_registrations": True},
    headers=admin_auth_headers,
  )


def test_report_analysis_disabled_blocks_non_admin(client, auth_headers, admin_auth_headers, app_ctx):
  disabled = client.patch(
    "/api/admin/settings",
    json={"ai_report_analysis_enabled": False},
    headers=admin_auth_headers,
  )
  assert disabled.status_code == 200

  resp = client.post(
    "/api/analysis",
    json={"report_text": "Hemoglobin: 12 g/dL"},
    headers=auth_headers,
  )
  assert resp.status_code == 403
  assert resp.get_json().get("data", {}).get("error_code") == "feature_disabled"

  # restore
  client.patch(
    "/api/admin/settings",
    json={"ai_report_analysis_enabled": True},
    headers=admin_auth_headers,
  )
