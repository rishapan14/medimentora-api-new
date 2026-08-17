"""Educational healthy X-ray comparison tests (real reference images only)."""

from __future__ import annotations

import io

from tests.conftest import make_png_bytes
from tests.test_xray_api import _clinical_form


def _seed_real_refs(lib_path):
  from pathlib import Path

  root = Path(lib_path)
  specs = [
    ("chest", "pa", "adult", "male", "chest_pa_adult_male_01.png"),
    ("chest", "pa", "adult", "female", "chest_pa_adult_female_01.png"),
    ("chest", "pa", "adult", "unisex", "chest_pa_adult_unisex_01.png"),
  ]
  for body, proj, age, gender, name in specs:
    folder = root / body / proj / age / gender
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(make_png_bytes(asymmetric=False))


def test_comparison_service_fallback_no_image(app_ctx, tmp_path, monkeypatch):
  from flask import current_app
  from types import SimpleNamespace

  from app.services.xray.comparison_service import XrayComparisonService
  from app.services.xray.reference_library import ReferenceLibraryService

  lib = tmp_path / "cmp_refs"
  lib.mkdir()
  _seed_real_refs(lib)
  monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(lib))
  monkeypatch.setitem(current_app.config, "XRAY_AUTO_SEED_REFERENCES", False)
  ReferenceLibraryService.rebuild_catalog_from_disk()
  from app.services.xray.reference_catalog_service import ReferenceCatalogService
  ReferenceCatalogService.sync()

  row = SimpleNamespace(
    id=1,
    possible_findings=[{"label": "Possible Lung Opacity", "probability": 0.7, "certainty": "possible"}],
    confidence=0.7,
    body_part="Chest",
    patient_age=58,
    gender="Male",
    symptoms="Cough",
    reason_for_exam="PA chest for chronic cough",
    smoking_history="Former Smoker",
    filename="chest_pa.png",
    clinical_extras={"projection": "PA"},
    patient_clinical_dict=lambda: {
      "patient_age": 58,
      "gender": "Male",
      "body_part": "Chest",
      "projection": "PA",
      "symptoms": "Cough",
      "reason_for_exam": "PA chest for chronic cough",
      "smoking_history": "Former Smoker",
    },
    learning_recommendations=[],
    structured_explanation={},
    reference_image_path=None,
    comparison_summary=None,
  )

  selection = ReferenceLibraryService.select_for_xray_row(row)
  assert selection.success
  assert selection.primary.projection == "PA"
  payload = XrayComparisonService._build_llm_payload(row, selection)
  assert "image" not in payload
  assert payload["healthy_reference"]["body_part"] == "Chest"
  assert payload["healthy_reference"]["projection"] == "PA"
  assert "absolute_path" not in payload["healthy_reference"]

  structured = XrayComparisonService._fallback_comparison(payload)
  assert "Compared with the educational reference image" in structured["comparison_summary"]
  assert structured["image_sent_to_llm"] is False


def test_compare_api_persists_fields(client, auth_headers, app, tmp_path, monkeypatch):
  from app.services.xray.reference_library import ReferenceLibraryService

  lib = tmp_path / "api_cmp_refs"
  lib.mkdir()
  _seed_real_refs(lib)
  with app.app_context():
    from flask import current_app

    monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(lib))
    monkeypatch.setitem(current_app.config, "XRAY_AUTO_COMPARISON", False)
    monkeypatch.setitem(current_app.config, "XRAY_AUTO_SEED_REFERENCES", False)
    ReferenceLibraryService.rebuild_catalog_from_disk()
    from app.services.xray.reference_catalog_service import ReferenceCatalogService
    ReferenceCatalogService.sync()

  raw = make_png_bytes(asymmetric=True)
  data = _clinical_form()
  data["files"] = (io.BytesIO(raw), "compare_me.png")
  analyze = client.post("/api/xray/analyze", data=data, headers=auth_headers)
  assert analyze.status_code in (200, 422), analyze.get_data(as_text=True)
  xray = ((analyze.get_json().get("data") or {}).get("analyses") or [{}])[0].get("xray") or {}
  xray_id = xray.get("id")
  assert xray_id

  missing = client.get(f"/api/xray/{xray_id}/compare", headers=auth_headers)
  if missing.status_code == 404:
    generated = client.post(f"/api/xray/{xray_id}/compare", headers=auth_headers)
    assert generated.status_code == 200, generated.get_data(as_text=True)
    payload = generated.get_json()["data"]
  else:
    payload = missing.get_json()["data"]
    regenerated = client.post(
      f"/api/xray/{xray_id}/compare?force=true",
      headers=auth_headers,
    )
    assert regenerated.status_code == 200
    payload = regenerated.get_json()["data"]

  comparison = payload["comparison"]
  assert comparison["success"] is True
  assert comparison["safety"]["image_sent_to_llm"] is False
  assert comparison["reference"]["body_part"] == "Chest"
  assert comparison["reference"]["projection"] == "PA"
  assert "Compared with" in comparison["comparison_summary"]
  learning = comparison.get("learning_recommendations") or []
  assert learning
  assert any(r.get("comparison_aware") for r in learning)

  detail = client.get(f"/api/xray/{xray_id}?include_explanation=true", headers=auth_headers)
  xray_detail = detail.get_json()["data"]["xray"]
  assert xray_detail["has_comparison"] is True
  assert xray_detail["reference_image_path"]
  assert xray_detail["comparison_summary"]

  ref_file = client.get(f"/api/xray/{xray_id}/reference", headers=auth_headers)
  assert ref_file.status_code == 200
  assert ref_file.mimetype.startswith("image/")

  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)
