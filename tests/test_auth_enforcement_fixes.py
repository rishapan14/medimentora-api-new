"""Regression tests for auth/settings enforcement bugfixes."""

from __future__ import annotations


def _student_headers(client):
  resp = client.post(
    "/api/auth/login",
    json={"email": "student@clinical.com", "password": "student123"},
  )
  if resp.status_code != 200:
    return None
  token = resp.get_json()["data"]["access_token"]
  return {"Authorization": f"Bearer {token}"}


def test_inactive_user_jwt_is_rejected(client, app_ctx):
  from app.extensions import db
  from app.models.user_model import User

  headers = _student_headers(client)
  if not headers:
    return

  user = User.query.filter_by(email="student@clinical.com").first()
  assert user is not None
  user.is_active = False
  db.session.commit()
  try:
    resp = client.get("/api/learning/courses", headers=headers)
    assert resp.status_code in (401, 403)
  finally:
    user.is_active = True
    db.session.commit()


def test_demote_restores_previous_clinical_role(client, admin_auth_headers, app_ctx):
  from app.constants import ROLE_DOCTOR
  from app.extensions import db
  from app.models.user_model import User

  target = User.query.filter(User.role != "admin").first()
  assert target is not None
  target.role = ROLE_DOCTOR
  target.previous_role = None
  db.session.commit()

  promote = client.patch(
    f"/api/admin/users/{target.id}/role",
    json={"role": "admin"},
    headers=admin_auth_headers,
  )
  assert promote.status_code == 200
  assert promote.get_json()["data"]["user"]["role"] == "admin"

  demote = client.patch(
    f"/api/admin/users/{target.id}/role",
    json={"role": "user"},
    headers=admin_auth_headers,
  )
  assert demote.status_code == 200
  body = demote.get_json()["data"]["user"]
  assert body["role"] == ROLE_DOCTOR
  assert body["is_admin"] is False
