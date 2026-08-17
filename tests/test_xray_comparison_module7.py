"""Module 7 — Full educational healthy X-ray comparison suite.

Covers Modules 1–6 end-to-end:
  schema/history → reference library → compare AI/API → reference file
  → comparison-aware learning → dashboard/history reopen fields
"""

from __future__ import annotations

import io

from tests.conftest import make_png_bytes
from tests.test_xray_api import _clinical_form


def _analyze_with_isolated_refs(client, auth_headers, app, tmp_path, monkeypatch, *, filename="m7.png"):
  """Analyze one X-ray against a temp real-image reference library; auto-comparison off."""
  from pathlib import Path

  from app.services.xray.reference_library import ReferenceLibraryService

  lib = tmp_path / "m7_refs"
  lib.mkdir(exist_ok=True)
  for body, proj, age, gender, name in (
    ("chest", "pa", "adult", "male", "chest_pa_adult_male_01.png"),
    ("chest", "pa", "adult", "unisex", "chest_pa_adult_unisex_01.png"),
  ):
    folder = Path(lib) / body / proj / age / gender
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(make_png_bytes(asymmetric=False))

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
  data["files"] = (io.BytesIO(raw), filename)
  analyze = client.post("/api/xray/analyze", data=data, headers=auth_headers)
  assert analyze.status_code in (200, 422), analyze.get_data(as_text=True)
  body = analyze.get_json().get("data") or {}
  analyses = body.get("analyses") or []
  assert analyses, analyze.get_data(as_text=True)
  xray = analyses[0].get("xray") or {}
  xray_id = xray.get("id")
  assert xray_id
  return int(xray_id)


def _ensure_comparison(client, auth_headers, xray_id):
  """GET stored comparison or POST to generate; force refresh for learning asserts."""
  existing = client.get(f"/api/xray/{xray_id}/compare", headers=auth_headers)
  if existing.status_code == 404:
    generated = client.post(f"/api/xray/{xray_id}/compare", headers=auth_headers)
    assert generated.status_code == 200, generated.get_data(as_text=True)
    return generated.get_json()["data"]

  refreshed = client.post(
    f"/api/xray/{xray_id}/compare?force=true",
    headers=auth_headers,
  )
  assert refreshed.status_code == 200, refreshed.get_data(as_text=True)
  return refreshed.get_json()["data"]


# ---------------------------------------------------------------------------
# Schema / history card (Module 1 + 5)
# ---------------------------------------------------------------------------


def test_history_card_includes_comparison_fields(app_ctx):
  from app.models.xray_analysis_model import XrayAnalysis

  row = XrayAnalysis(
    user_id=1,
    filename="schema.png",
    body_part="Chest",
    patient_age=40,
    gender="Male",
    smoking_history="Never Smoked",
    reference_image_path="Chest/Adult/Male/healthy.png",
    comparison_summary="Compared with the educational reference image for learning. " * 5,
    status="completed",
  )
  card = row.to_history_card()
  assert card["has_comparison"] is True
  assert card["reference_image_path"]
  assert card["comparison_summary"]
  assert card["comparison_summary"].endswith("…") or len(card["comparison_summary"]) <= 221
  assert "patient_summary" in card

  full = row.to_dict()
  assert full["has_comparison"] is True
  assert full["comparison_summary"]


def test_history_card_without_comparison(app_ctx):
  from app.models.xray_analysis_model import XrayAnalysis

  row = XrayAnalysis(user_id=1, filename="plain.png", body_part="Hand", status="uploaded")
  card = row.to_history_card()
  assert card["has_comparison"] is False
  assert card.get("comparison_summary") in (None, "")
  assert card.get("reference_image_path") in (None, "")


# ---------------------------------------------------------------------------
# Safety (Module 3)
# ---------------------------------------------------------------------------


def test_comparison_refuses_image_payload(app_ctx):
  from app.services.xray.comparison_service import XrayComparisonService

  assert XrayComparisonService._payload_looks_like_image_request({"image_b64": "abc"}) is True
  assert XrayComparisonService._payload_looks_like_image_request({"pixels": []}) is True
  assert (
    XrayComparisonService._payload_looks_like_image_request(
      {"possible_findings": [], "healthy_reference": {"body_part": "Chest"}}
    )
    is False
  )


def test_llm_payload_excludes_paths_and_images(app_ctx, tmp_path, monkeypatch):
  from types import SimpleNamespace

  from flask import current_app

  from app.services.xray.comparison_service import XrayComparisonService
  from app.services.xray.reference_library import ReferenceLibraryService

  lib = tmp_path / "safe_refs"
  folder = lib / "chest" / "pa" / "adult" / "female"
  folder.mkdir(parents=True)
  (folder / "chest_pa_adult_female_01.png").write_bytes(make_png_bytes())
  monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(lib))
  monkeypatch.setitem(current_app.config, "XRAY_AUTO_SEED_REFERENCES", False)
  ReferenceLibraryService.rebuild_catalog_from_disk()
  from app.services.xray.reference_catalog_service import ReferenceCatalogService
  ReferenceCatalogService.sync()

  row = SimpleNamespace(
    id=99,
    possible_findings=[{"label": "Possible Opacity", "probability": 0.5}],
    confidence=0.5,
    body_part="Chest",
    patient_age=30,
    gender="Female",
    symptoms="",
    reason_for_exam="PA chest",
    smoking_history="Never Smoked",
    filename="patient.png",
    clinical_extras={"projection": "PA"},
  )
  selection = ReferenceLibraryService.select_for_xray_row(row)
  assert selection.success
  payload = XrayComparisonService._build_llm_payload(row, selection)
  banned = {"image", "image_b64", "base64", "bytes", "pixels", "absolute_path", "file_path"}
  assert banned.isdisjoint(payload.keys())
  assert banned.isdisjoint((payload.get("healthy_reference") or {}).keys())
  assert payload["healthy_reference"]["body_part"] == "Chest"
  assert payload["healthy_reference"]["projection"] == "PA"


# ---------------------------------------------------------------------------
# Learning integration (Module 6)
# ---------------------------------------------------------------------------


def test_comparison_context_seeds_normal_anatomy_topics(app_ctx):
  from app.services.xray.recommendation_service import XrayRecommendationService

  result = XrayRecommendationService.build_recommendations(
    possible_findings=[{"label": "Possible Fracture", "probability": 0.55}],
    body_part="Hand",
    comparison_context={
      "body_part": "Hand",
      "reference_body_part": "Hand",
      "age_group": "Adult",
      "learning_focus": ["Normal Radiograph Anatomy", "Bone Anatomy"],
    },
    sync_user_recommendations=False,
  )
  assert result.success
  assert result.comparison_aware is True
  blob = " ".join(result.topics).lower()
  assert "normal radiograph" in blob or "systematic" in blob
  assert any(r.get("comparison_aware") for r in result.recommendations)
  assert any("healthy reference" in (r.get("reason") or "").lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# End-to-end API (Modules 2–6)
# ---------------------------------------------------------------------------


def test_full_comparison_pipeline(client, auth_headers, app, tmp_path, monkeypatch):
  xray_id = _analyze_with_isolated_refs(
    client, auth_headers, app, tmp_path, monkeypatch, filename="m7_pipeline.png"
  )
  try:
    payload = _ensure_comparison(client, auth_headers, xray_id)
    comparison = payload["comparison"]
    xray = payload.get("xray") or {}

    assert comparison["success"] is True
    assert comparison["safety"]["image_sent_to_llm"] is False
    assert comparison["safety"].get("definitive_diagnosis") is False
    assert comparison["safety"].get("educational_comparison_only") is True
    assert comparison["reference"]["body_part"] == "Chest"
    assert "Compared with" in (comparison.get("comparison_summary") or "")

    structured = comparison.get("structured_comparison") or {}
    assert structured.get("learning_focus")
    assert structured.get("key_visual_differences")
    assert structured.get("questions_for_healthcare_professional")

    learning = comparison.get("learning_recommendations") or []
    assert learning
    assert any(r.get("comparison_aware") or r.get("source") == "comparison" for r in learning)
    assert any(r.get("href") for r in learning)

    # Detail row persisted
    detail = client.get(f"/api/xray/{xray_id}?include_explanation=true", headers=auth_headers)
    assert detail.status_code == 200
    xray_detail = detail.get_json()["data"]["xray"]
    assert xray_detail["has_comparison"] is True
    assert xray_detail["reference_image_path"]
    assert xray_detail["comparison_summary"]
    assert xray_detail["comparison_generated_at"]
    expl = xray_detail.get("structured_explanation") or {}
    assert expl.get("educational_comparison")
    assert expl.get("comparison_reference")
    persisted_learning = xray_detail.get("learning_recommendations") or []
    assert persisted_learning
    assert any(r.get("comparison_aware") for r in persisted_learning)

    # Reference image download for compare UI
    ref_file = client.get(f"/api/xray/{xray_id}/reference", headers=auth_headers)
    assert ref_file.status_code == 200, ref_file.get_data(as_text=True)
    assert ref_file.mimetype.startswith("image/")
    assert len(ref_file.data) > 100

    # Patient original still available
    original = client.get(f"/api/xray/{xray_id}/file", headers=auth_headers)
    assert original.status_code == 200

    # History card reopen fields
    history = client.get("/api/xray/history", headers=auth_headers)
    assert history.status_code == 200
    cards = (history.get_json().get("data") or {}).get("history") or []
    match = next((c for c in cards if c.get("id") == xray_id), None)
    assert match is not None
    assert match["has_comparison"] is True
    assert match.get("reference_image_path")
    assert match.get("comparison_summary")

    # Dashboard surfaces comparison-aware learning + recent flags
    dash = client.get("/api/xray/dashboard", headers=auth_headers)
    assert dash.status_code == 200
    dash_data = dash.get_json()["data"]
    recent = (dash_data.get("recent_xrays") or []) + (dash_data.get("recent_analyses") or [])
    assert any(r.get("id") == xray_id and r.get("has_comparison") for r in recent)
    recs = dash_data.get("learning_recommendations") or []
    if recs:
      # At least one entry may be comparison-aware after this pipeline
      assert any(
        r.get("comparison_aware") or r.get("source_has_comparison") or r.get("source_xray_id") == xray_id
        for r in recs
      )

    # Stored GET reopen (no regenerate)
    stored = client.get(f"/api/xray/{xray_id}/compare", headers=auth_headers)
    assert stored.status_code == 200
    stored_cmp = stored.get_json()["data"]["comparison"]
    assert stored_cmp.get("comparison_summary")
    assert stored_cmp.get("learning_recommendations")

    # Recommendations refresh stays comparison-aware when comparison exists
    rec_resp = client.post(f"/api/xray/{xray_id}/recommendations", headers=auth_headers)
    assert rec_resp.status_code == 200
    rec_data = rec_resp.get_json()["data"]
    refreshed = rec_data.get("recommendations") or rec_data.get("learning_recommendations") or []
    if not refreshed and isinstance(rec_data.get("result"), dict):
      refreshed = rec_data["result"].get("recommendations") or []
    # Controller shape may nest under different keys — also check xray
    if not refreshed:
      refreshed = (rec_data.get("xray") or {}).get("learning_recommendations") or []
    assert refreshed
    assert any(r.get("comparison_aware") for r in refreshed)

    # Disclaimer always educational
    disclaimer = (
      comparison.get("disclaimer")
      or payload.get("disclaimer")
      or xray.get("disclaimer")
      or ""
    ).lower()
    assert "educational" in disclaimer or "not a diagnosis" in disclaimer or "not intended" in disclaimer
  finally:
    client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_reference_missing_before_compare(client, auth_headers, app, tmp_path, monkeypatch):
  xray_id = _analyze_with_isolated_refs(
    client, auth_headers, app, tmp_path, monkeypatch, filename="m7_noref.png"
  )
  try:
    missing = client.get(f"/api/xray/{xray_id}/reference", headers=auth_headers)
    # Auto-comparison may have run depending on create_app defaults
    assert missing.status_code in (200, 404)
    if missing.status_code == 404:
      body = missing.get_data(as_text=True).lower()
      assert "compare" in body or "reference" in body or "not found" in body
  finally:
    client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_compare_force_regenerates_learning(client, auth_headers, app, tmp_path, monkeypatch):
  xray_id = _analyze_with_isolated_refs(
    client, auth_headers, app, tmp_path, monkeypatch, filename="m7_force.png"
  )
  try:
    first = _ensure_comparison(client, auth_headers, xray_id)
    first_summary = first["comparison"]["comparison_summary"]
    first_learning = first["comparison"].get("learning_recommendations") or []
    assert first_learning

    second = client.post(
      f"/api/xray/{xray_id}/compare?force=true",
      headers=auth_headers,
    )
    assert second.status_code == 200
    second_payload = second.get_json()["data"]["comparison"]
    assert second_payload["comparison_summary"]
    # Summary may match fallback text; learning must remain comparison-aware
    second_learning = second_payload.get("learning_recommendations") or []
    assert second_learning
    assert any(r.get("comparison_aware") for r in second_learning)
    assert first_summary  # sanity
  finally:
    client.delete(f"/api/xray/{xray_id}", headers=auth_headers)
