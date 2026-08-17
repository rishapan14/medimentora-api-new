"""Module 10 — Admin platform Reports API tests."""

from __future__ import annotations


def test_admin_reports_requires_admin(client, auth_headers):
  resp = client.get("/api/admin/reports/overview", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_reports_overview_ok(client, admin_auth_headers):
  resp = client.get("/api/admin/reports/overview", headers=admin_auth_headers)
  assert resp.status_code == 200
  data = resp.get_json()["data"]
  assert "users" in data
  assert "ai" in data
  assert "learning" in data
  assert "assessments" in data
  assert "recent_activity" in data
  assert data["users"]["total"] >= 1
  assert "report_analyses" in data["ai"]
  assert "xray_analyses" in data["ai"]
  assert "average_quiz_score" in data["assessments"]


def test_admin_export_users_csv(client, admin_auth_headers):
  resp = client.get("/api/admin/reports/export/users.csv", headers=admin_auth_headers)
  assert resp.status_code == 200
  assert "text/csv" in (resp.content_type or "")
  body = resp.get_data(as_text=True)
  assert "email" in body
  assert "admin@clinical.com" in body


def test_admin_export_overview_csv(client, admin_auth_headers):
  resp = client.get("/api/admin/reports/export/overview.csv", headers=admin_auth_headers)
  assert resp.status_code == 200
  body = resp.get_data(as_text=True)
  assert "section" in body
  assert "users" in body
  assert "metric" in body