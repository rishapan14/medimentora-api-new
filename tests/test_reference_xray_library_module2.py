"""Module 2 — Reference X-Ray Library backend tests."""

from __future__ import annotations

import io

import pytest
from werkzeug.datastructures import FileStorage

from tests.conftest import make_filestorage, make_png_bytes


VALID_META = {
  "body_part": "Chest",
  "projection": "PA",
  "orientation": "Unknown",
  "age_group": "Adult",
  "gender": "Unisex",
  "difficulty": "Beginner",
  "source": "Test teaching file",
  "license": "Internal test",
  "description": "Healthy educational chest radiograph",
  "anatomical_notes": "Lung fields, heart border",
  "title": "Healthy Chest PA Adult",
}


@pytest.fixture
def library_service(app_ctx, tmp_path, monkeypatch):
  from flask import current_app

  from app.services.xray.reference_xray_library_service import ReferenceXrayLibraryService

  lib = tmp_path / "reference_library_v2"
  lib.mkdir()
  monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(lib))
  return ReferenceXrayLibraryService, str(lib)


def test_validate_metadata_requires_fields(library_service):
  service, _ = library_service
  result = service.validate_metadata({"body_part": "Chest"}, for_upload=True)
  assert result.success is False
  assert result.error_code == "validation_error"
  fields = {e["field"] for e in result.field_errors}
  assert "projection" in fields
  assert "orientation" in fields
  assert "age_group" in fields
  assert "gender" in fields


def test_validate_metadata_rejects_invalid_enum(library_service):
  service, _ = library_service
  bad = {**VALID_META, "projection": "NotAView"}
  result = service.validate_metadata(bad, for_upload=True)
  assert result.success is False
  assert any(e["field"] == "projection" for e in result.field_errors)


def test_validate_metadata_requires_required_strings(library_service):
  service, _ = library_service
  bad = {**VALID_META}
  bad["source"] = ""
  result = service.validate_metadata(bad, for_upload=True)
  assert result.success is False
  assert any(e["field"] == "source" for e in result.field_errors)


def test_validate_metadata_ok(library_service):
  service, _ = library_service
  result = service.validate_metadata(VALID_META, for_upload=True)
  assert result.success is True
  assert result.data["metadata"]["body_part"] == "Chest"
  assert result.data["metadata"]["projection"] == "PA"


def test_upload_and_search(library_service):
  service, root = library_service
  fs = make_filestorage("chest_pa.png")
  result = service.upload(fs, VALID_META, uploaded_by=None)
  assert result.success is True, result.message
  ref = result.data["reference"]
  assert ref["body_part"] == "Chest"
  assert ref["orientation"] == "Unknown"
  assert ref["image_path"]
  assert ref["public_id"]
  assert ref["image_exists"] is True

  rows, total = service.search(body_part="Chest", projection="PA", is_active=True)
  assert total >= 1
  assert any(r.id == ref["id"] for r in rows)


def test_upload_fails_without_metadata(library_service):
  service, _ = library_service
  fs = make_filestorage("chest.png")
  result = service.upload(fs, {"body_part": "Chest"}, uploaded_by=None)
  assert result.success is False
  assert result.error_code == "validation_error"


def test_bulk_upload_zip(library_service):
  import io
  import zipfile

  service, _ = library_service
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("chest_a.png", make_png_bytes())
    zf.writestr("nested/chest_b.png", make_png_bytes())
    zf.writestr("readme.txt", b"ignore me")
  buf.seek(0)
  zip_fs = FileStorage(stream=buf, filename="refs.zip", content_type="application/zip")
  result = service.bulk_upload_zip(zip_fs, VALID_META)
  assert result.success is True, result.message
  assert result.data["uploaded"] == 2
  assert result.data["total"] == 2


def test_bulk_upload(library_service):
  service, _ = library_service
  files = [make_filestorage(f"chest_{i}.png") for i in range(3)]
  result = service.bulk_upload(files, VALID_META)
  assert result.success is True
  assert result.data["uploaded"] == 3
  assert result.data["total"] == 3


def test_update_deactivate_reactivate_delete(library_service):
  service, _ = library_service
  uploaded = service.upload(make_filestorage("knee.png"), {
    **VALID_META,
    "body_part": "Knee",
    "projection": "Lateral",
    "title": "Healthy Knee Lateral",
  })
  assert uploaded.success
  ref_id = uploaded.data["reference"]["id"]

  updated = service.update_metadata(ref_id, {
    "description": "Updated educational notes",
    "difficulty": "Intermediate",
  })
  assert updated.success
  assert updated.data["reference"]["difficulty"] == "Intermediate"
  assert "Updated educational" in (updated.data["reference"]["description"] or "")

  deactivated = service.set_active(ref_id, active=False)
  assert deactivated.success
  assert deactivated.data["reference"]["is_active"] is False
  rows, total = service.search(body_part="Knee", is_active=True)
  assert all(r.id != ref_id for r in rows)

  reactivated = service.set_active(ref_id, active=True)
  assert reactivated.success
  assert reactivated.data["reference"]["is_active"] is True

  deleted = service.delete(ref_id, delete_files=True)
  assert deleted.success
  assert service.get_by_id(ref_id) is None


def test_storage_stats(library_service):
  service, _ = library_service
  service.upload(make_filestorage("stats.png"), VALID_META)
  stats = service.storage_stats()
  assert stats["total"] >= 1
  assert stats["active"] >= 1
  assert stats["bytes_on_disk"] > 0
  assert "Chest" in stats["by_body_part"]


def test_path_traversal_blocked(library_service):
  service, _ = library_service
  assert service.resolve_path("../secrets.txt") is None
  assert service.resolve_path("..\\..\\app\\config.py") is None


def test_form_options_taxonomy(library_service):
  service, _ = library_service
  options = service.form_options()
  assert "Finger" in options["body_parts"]
  assert "Skyline" in options["projections"]
  assert "Infant" in options["age_groups"]
  assert "Bilateral" in options["orientations"]
  assert "Unknown" in options["genders"]
  assert set(options["required_upload_fields"]) >= {
    "body_part",
    "projection",
    "orientation",
    "age_group",
    "gender",
  }


def test_admin_api_upload_requires_admin(client, auth_headers, app, tmp_path, monkeypatch):
  """Student token must be forbidden from admin library endpoints."""
  with app.app_context():
    from flask import current_app

    monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(tmp_path / "lib"))

  raw = make_png_bytes()
  resp = client.post(
    "/api/xray/admin/references",
    data={
      "file": (io.BytesIO(raw), "chest.png"),
      **VALID_META,
    },
    content_type="multipart/form-data",
    headers=auth_headers,
  )
  assert resp.status_code == 403


def test_admin_api_flow(client, app, tmp_path, monkeypatch):
  """Full admin API path when admin demo account is available."""
  login = client.post(
    "/api/auth/login",
    json={"email": "admin@clinical.com", "password": "admin123"},
  )
  if login.status_code != 200:
    pytest.skip("Admin demo login unavailable")
  token = (login.get_json() or {}).get("data", {}).get("access_token")
  if not token:
    pytest.skip("No admin access token")
  headers = {"Authorization": f"Bearer {token}"}

  with app.app_context():
    from flask import current_app

    lib = tmp_path / "admin_api_lib"
    lib.mkdir()
    monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(lib))

  # Missing metadata → validation error
  bad = client.post(
    "/api/xray/admin/references",
    data={"file": (io.BytesIO(make_png_bytes()), "chest.png"), "body_part": "Chest"},
    content_type="multipart/form-data",
    headers=headers,
  )
  assert bad.status_code in (400, 422)

  good = client.post(
    "/api/xray/admin/references",
    data={
      "file": (io.BytesIO(make_png_bytes()), "chest.png"),
      **VALID_META,
    },
    content_type="multipart/form-data",
    headers=headers,
  )
  assert good.status_code == 201, good.get_json()
  ref = good.get_json()["data"]["reference"]
  ref_id = ref["id"]

  listed = client.get(
    "/api/xray/admin/references?body_part=Chest&q=Healthy",
    headers=headers,
  )
  assert listed.status_code == 200
  assert listed.get_json()["data"]["total"] >= 1

  preview = client.get(f"/api/xray/admin/references/{ref_id}/file", headers=headers)
  assert preview.status_code == 200
  assert len(preview.data) > 50

  deact = client.post(f"/api/xray/admin/references/{ref_id}/deactivate", headers=headers)
  assert deact.status_code == 200
  assert deact.get_json()["data"]["reference"]["is_active"] is False

  react = client.post(f"/api/xray/admin/references/{ref_id}/reactivate", headers=headers)
  assert react.status_code == 200

  stats = client.get("/api/xray/admin/references/stats", headers=headers)
  assert stats.status_code == 200
  assert "storage" in stats.get_json()["data"]

  deleted = client.delete(f"/api/xray/admin/references/{ref_id}", headers=headers)
  assert deleted.status_code == 200
