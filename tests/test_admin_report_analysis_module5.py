"""Module 5 — Admin AI Report Analysis monitoring API tests."""

from __future__ import annotations


def test_admin_list_report_analyses_requires_admin(client, auth_headers):
  resp = client.get("/api/admin/report-analyses", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_list_report_analyses_ok(client, admin_auth_headers):
  resp = client.get("/api/admin/report-analyses?limit=20", headers=admin_auth_headers)
  assert resp.status_code == 200
  data = resp.get_json()["data"]
  assert "analyses" in data
  assert "stats" in data
  assert "total" in data
  assert isinstance(data["analyses"], list)
  assert "total" in data["stats"]
  assert "unique_users" in data["stats"]


def test_admin_report_analysis_get_and_delete(client, admin_auth_headers, app_ctx):
  from app.extensions import db
  from app.models.report_analysis_model import ReportAnalysis
  from app.models.user_model import User

  user = User.query.filter_by(email="student@clinical.com").first()
  assert user is not None

  row = ReportAnalysis(
    user_id=user.id,
    report_id=None,
    report_text="Hemoglobin: 10.2 g/dL (12-16)",
    simple_explanation="Hemoglobin is below the typical reference range.",
    abnormal_values=[{"name": "Hemoglobin", "value": 10.2}],
    possible_diseases=[{"name": "Anemia", "confidence": "low"}],
    medical_terms=[{"term": "Hemoglobin"}],
    learning_topics=["CBC interpretation"],
    full_response={
      "report_type": "cbc",
      "analysis_mode": "rule_based",
      "simple_explanation": "Hemoglobin is below the typical reference range.",
      "abnormal_values": [{"name": "Hemoglobin", "value": 10.2}],
    },
  )
  db.session.add(row)
  db.session.commit()
  analysis_id = row.id

  listed = client.get(
    "/api/admin/report-analyses?q=Hemoglobin",
    headers=admin_auth_headers,
  )
  assert listed.status_code == 200
  ids = [a["id"] for a in listed.get_json()["data"]["analyses"]]
  assert analysis_id in ids

  detail = client.get(
    f"/api/admin/report-analyses/{analysis_id}",
    headers=admin_auth_headers,
  )
  assert detail.status_code == 200
  body = detail.get_json()["data"]["analysis"]
  assert body["id"] == analysis_id
  assert body["user_email"] == "student@clinical.com"
  assert body["report_type"] == "cbc"

  deleted = client.delete(
    f"/api/admin/report-analyses/{analysis_id}",
    headers=admin_auth_headers,
  )
  assert deleted.status_code == 200
  assert db.session.get(ReportAnalysis, analysis_id) is None


def test_admin_report_analysis_not_found(client, admin_auth_headers):
  resp = client.get("/api/admin/report-analyses/99999999", headers=admin_auth_headers)
  assert resp.status_code == 404
