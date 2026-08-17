"""Real healthy X-ray reference library tests (no placeholder drawings)."""

from __future__ import annotations

import os

import pytest

from tests.conftest import make_png_bytes


@pytest.fixture
def real_reference_library(app_ctx, tmp_path, monkeypatch):
  """Temp library with real PNG files under body/projection/age/gender."""
  from flask import current_app

  from app.services.xray.reference_library import ReferenceLibraryService

  lib = tmp_path / "reference_library"
  specs = [
    ("chest", "pa", "adult", "male", "chest_pa_adult_male_01.png"),
    ("chest", "pa", "adult", "female", "chest_pa_adult_female_01.png"),
    ("chest", "lateral", "adult", "unisex", "chest_lat_adult_unisex_01.png"),
    ("chest", "pa", "child", "unisex", "chest_pa_child_unisex_01.png"),
    ("hand", "ap", "adult", "unisex", "hand_ap_adult_unisex_01.png"),
    ("knee", "lateral", "adult", "unisex", "knee_lat_adult_unisex_01.png"),
  ]
  for body, proj, age, gender, filename in specs:
    folder = lib / body / proj / age / gender
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_bytes(make_png_bytes(asymmetric=False))

  monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(lib))
  monkeypatch.setitem(current_app.config, "XRAY_AUTO_SEED_REFERENCES", False)
  catalog = ReferenceLibraryService.rebuild_catalog_from_disk()
  assert catalog["references"]
  assert all("placeholder" not in (r.get("notes") or "").lower() for r in catalog["references"])
  from app.services.xray.reference_library_manager import ReferenceLibraryManager

  sync = ReferenceLibraryManager.sync_from_disk()
  assert sync.success

  from app.services.xray.reference_catalog_service import ReferenceCatalogService

  cat_result = ReferenceCatalogService.sync()
  assert cat_result["success"]

  return str(lib)


def test_rebuild_catalog_from_disk_taxonomy(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  refs = ReferenceLibraryService.list_references()
  assert len(refs) >= 6
  chest = [r for r in refs if r.body_part == "Chest"]
  assert any(r.projection == "PA" and r.age_group == "Adult" and r.gender == "Male" for r in chest)
  assert any(r.projection == "Lateral" for r in chest)
  for ref in refs:
    assert os.path.isfile(ref.absolute_path)
    assert ref.projection in ("PA", "AP", "Lateral", "Oblique", "Other")


def test_seed_placeholders_does_not_draw(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  before = {r.id for r in ReferenceLibraryService.list_references()}
  ReferenceLibraryService.seed_placeholders()
  after = {r.id for r in ReferenceLibraryService.list_references()}
  assert before == after


def test_projection_matching_prefers_pa(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  result = ReferenceLibraryService.select_reference(
    body_part="Chest",
    patient_age=40,
    gender="Male",
    projection="PA",
  )
  assert result.success
  assert result.primary.body_part == "Chest"
  assert result.primary.projection == "PA"
  assert result.matched_projection == "PA"
  assert result.gender_used is True
  assert result.primary.gender == "Male"


def test_lateral_not_confused_with_pa(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  result = ReferenceLibraryService.select_reference(
    body_part="Chest",
    patient_age=35,
    gender="Female",
    projection="Lateral",
  )
  assert result.success
  assert result.primary.projection == "Lateral"


def test_child_age_group_selection(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  assert ReferenceLibraryService.age_group_from_age(10) == "Child"
  result = ReferenceLibraryService.select_reference(
    body_part="Chest",
    patient_age=8,
    gender="Female",
    projection="PA",
  )
  assert result.success
  assert result.matched_age_group == "Child"
  assert result.primary.age_group == "Child"


def test_gender_not_forced_for_hand(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  result = ReferenceLibraryService.select_reference(
    body_part="Hand",
    patient_age=30,
    gender="Female",
    projection="AP",
  )
  assert result.success
  assert result.gender_used is False
  assert result.primary.body_part == "Hand"
  assert result.primary.gender == "Unisex"


def test_closest_educational_when_no_exact_body_part(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  result = ReferenceLibraryService.select_reference(
    body_part="Dental",
    patient_age=40,
    projection="PA",
  )
  assert result.success is True
  assert result.primary is not None
  assert "closest educational" in (result.message or "").lower()


def test_soft_empty_when_library_has_no_images(app_ctx, tmp_path, monkeypatch):
  from flask import current_app

  from app.services.xray.reference_library import ReferenceLibraryService, EMPTY_LIBRARY_MESSAGE

  empty = tmp_path / "empty_refs"
  empty.mkdir()
  monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(empty))
  monkeypatch.setitem(current_app.config, "XRAY_AUTO_SEED_REFERENCES", False)
  ReferenceLibraryService.rebuild_catalog_from_disk()

  result = ReferenceLibraryService.select_reference(
    body_part="Chest",
    patient_age=40,
    projection="PA",
  )
  assert result.success is False
  assert result.error_code == "empty_library"
  assert EMPTY_LIBRARY_MESSAGE in (result.message or "")



def test_detect_projection_from_text(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  assert (
    ReferenceLibraryService.detect_projection(reason_for_exam="PA chest for cough") == "PA"
  )
  assert ReferenceLibraryService.detect_projection(filename="knee_lateral.png") == "Lateral"
  assert ReferenceLibraryService.detect_projection(explicit="Oblique") == "Oblique"


def test_path_traversal_blocked(real_reference_library):
  from app.services.xray.reference_library import ReferenceLibraryService

  assert ReferenceLibraryService.resolve_file("../secrets.txt") is None
  assert ReferenceLibraryService.resolve_file("../../app/config.py") is None


def test_reference_api_list_and_select(client, auth_headers, app, tmp_path, monkeypatch):
  from app.services.xray.reference_library import ReferenceLibraryService

  lib = tmp_path / "api_refs"
  folder = lib / "chest" / "pa" / "adult" / "female"
  folder.mkdir(parents=True)
  (folder / "chest_pa_adult_female_01.png").write_bytes(make_png_bytes())

  with app.app_context():
    from flask import current_app

    monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(lib))
    monkeypatch.setitem(current_app.config, "XRAY_AUTO_SEED_REFERENCES", False)
    ReferenceLibraryService.rebuild_catalog_from_disk()
    from app.services.xray.reference_library_manager import ReferenceLibraryManager

    assert ReferenceLibraryManager.sync_from_disk().success
    from app.services.xray.reference_catalog_service import ReferenceCatalogService

    ReferenceCatalogService.sync()

  options = client.get("/api/xray/references/options", headers=auth_headers)
  assert options.status_code == 200
  data = options.get_json()["data"]
  assert data["library_ready"] is True
  assert "PA" in data["projections"]

  listed = client.get(
    "/api/xray/references?body_part=Chest&projection=PA",
    headers=auth_headers,
  )
  assert listed.status_code == 200
  refs = listed.get_json()["data"]["references"]
  assert refs
  assert all(r["projection"] == "PA" for r in refs)

  selected = client.get(
    "/api/xray/references/select",
    query_string={
      "body_part": "Chest",
      "patient_age": 42,
      "gender": "Female",
      "projection": "PA",
    },
    headers=auth_headers,
  )
  assert selected.status_code == 200
  primary = selected.get_json()["data"]["primary"]
  assert primary["body_part"] == "Chest"
  assert primary["projection"] == "PA"
  assert primary["exists"] is True

  file_resp = client.get(
    f"/api/xray/references/{primary['id']}/file",
    headers=auth_headers,
  )
  assert file_resp.status_code == 200
  assert file_resp.mimetype.startswith("image/")
  assert len(file_resp.data) > 100
