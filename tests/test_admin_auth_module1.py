"""Module 1 — Admin Panel role-based auth tests."""

from __future__ import annotations

from app.constants import ROLE_ADMIN, is_admin_role


def test_is_admin_role_helpers():
  assert is_admin_role("admin") is True
  assert is_admin_role("Admin") is True
  assert is_admin_role("user") is False
  assert is_admin_role("doctor") is False
  assert is_admin_role(None) is False


def test_user_to_dict_includes_is_admin(app_ctx):
  from app.models.user_model import User

  admin = User.query.filter_by(role=ROLE_ADMIN).first()
  if not admin:
    u = User(email="tmp_admin_check@test.local", full_name="T", role=ROLE_ADMIN)
    u.set_password("x")
    assert u.is_admin is True
    d = u.to_dict()
    assert d["is_admin"] is True
    assert d["isAdmin"] is True
    return

  payload = admin.to_dict()
  assert payload["role"] == ROLE_ADMIN
  assert payload["is_admin"] is True
  assert payload["isAdmin"] is True


def test_admin_api_rejects_non_admin(client, auth_headers):
  """auth_headers fixture is a normal user — must get 403 on admin routes."""
  resp = client.get("/api/xray/admin/references", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_api_allows_admin(client, admin_auth_headers):
  resp = client.get("/api/xray/admin/references?limit=5", headers=admin_auth_headers)
  assert resp.status_code == 200
  body = resp.get_json()
  assert body["status"] == "success"
