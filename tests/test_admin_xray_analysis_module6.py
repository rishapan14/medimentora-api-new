"""Module 6 — Admin AI X-Ray Analysis monitoring API tests."""

from __future__ import annotations


def test_admin_list_xray_analyses_requires_admin(client, auth_headers):
  resp = client.get("/api/admin/xray-analyses", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_list_xray_analyses_ok(client, admin_auth_headers):
  resp = client.get("/api/admin/xray-analyses?limit=20", headers=admin_auth_headers)
  assert resp.status_code == 200
  data = resp.get_json()["data"]
  assert "analyses" in data
  assert "stats" in data
  assert "total" in data
  assert isinstance(data["analyses"], list)
  assert "unique_users" in data["stats"]
  assert "by_status" in data["stats"]


def test_admin_xray_analysis_get_and_delete(client, admin_auth_headers, app_ctx, tmp_path):
  from app.extensions import db
  from app.models.user_model import User
  from app.models.xray_analysis_model import XRAY_STATUS_COMPLETED, XrayAnalysis

  user = User.query.filter_by(email="student@clinical.com").first()
  assert user is not None

  fake_file = tmp_path / "admin_module6_chest.png"
  fake_file.write_bytes(b"\x89PNG\r\n\x1a\nfake")

  row = XrayAnalysis(
    user_id=user.id,
    filename="admin_module6_chest.png",
    stored_filename="admin_module6_chest.png",
    file_path=str(fake_file),
    file_type="png",
    file_size=fake_file.stat().st_size,
    body_part="Chest",
    patient_age=45,
    gender="Male",
    status=XRAY_STATUS_COMPLETED,
    confidence=0.72,
    ai_summary="Possible opacity noted for educational review.",
    possible_findings=[{"label": "Opacity", "confidence": 0.72}],
    model_name="test-model",
    analysis_version="test",
  )
  db.session.add(row)
  db.session.commit()
  xray_id = row.id

  listed = client.get(
    "/api/admin/xray-analyses?q=admin_module6&body_part=Chest",
    headers=admin_auth_headers,
  )
  assert listed.status_code == 200
  ids = [a["id"] for a in listed.get_json()["data"]["analyses"]]
  assert xray_id in ids

  detail = client.get(
    f"/api/admin/xray-analyses/{xray_id}",
    headers=admin_auth_headers,
  )
  assert detail.status_code == 200
  body = detail.get_json()["data"]["analysis"]
  assert body["id"] == xray_id
  assert body["user_email"] == "student@clinical.com"
  assert body["body_part"] == "Chest"

  deleted = client.delete(
    f"/api/admin/xray-analyses/{xray_id}",
    headers=admin_auth_headers,
  )
  assert deleted.status_code == 200
  assert db.session.get(XrayAnalysis, xray_id) is None
  assert not fake_file.exists()


def test_admin_xray_analysis_not_found(client, admin_auth_headers):
  resp = client.get("/api/admin/xray-analyses/99999999", headers=admin_auth_headers)
  assert resp.status_code == 404
