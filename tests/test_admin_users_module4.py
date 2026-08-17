"""Module 4 — Admin user management API tests."""

from __future__ import annotations


def test_admin_list_users_requires_admin(client, auth_headers):
  resp = client.get("/api/admin/users", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_list_users_ok(client, admin_auth_headers):
  resp = client.get("/api/admin/users?limit=20", headers=admin_auth_headers)
  assert resp.status_code == 200
  data = resp.get_json()["data"]
  assert "users" in data
  assert "stats" in data
  assert data["stats"]["admins"] >= 1


def test_admin_can_set_user_role(client, admin_auth_headers, app_ctx):
  from app.models.user_model import User

  target = User.query.filter(User.role != "admin").first()
  assert target is not None
  original_role = target.role

  # Promote then demote
  promote = client.patch(
    f"/api/admin/users/{target.id}/role",
    json={"role": "admin"},
    headers=admin_auth_headers,
  )
  assert promote.status_code == 200
  assert promote.get_json()["data"]["user"]["is_admin"] is True

  demote = client.patch(
    f"/api/admin/users/{target.id}/role",
    json={"role": "user"},
    headers=admin_auth_headers,
  )
  assert demote.status_code == 200
  body = demote.get_json()["data"]["user"]
  assert body["is_admin"] is False
  assert body["panel_role"] == "User"
  # Clinical/system role is restored (not permanently wiped)
  assert body["role"] == original_role
  assert body["role"] != "admin"

def test_admin_cannot_demote_self(client, admin_auth_headers, app_ctx):
  from app.models.user_model import User

  me = User.query.filter_by(email="admin@clinical.com").first()
  assert me is not None
  resp = client.patch(
    f"/api/admin/users/{me.id}/role",
    json={"role": "user"},
    headers=admin_auth_headers,
  )
  assert resp.status_code == 403
