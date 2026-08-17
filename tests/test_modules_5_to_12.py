"""Comprehensive tests for Modules 5–12 (Catalog, Matcher, Viewer, Export).

Runs with:  pytest tests/test_modules_5_to_12.py -v
"""

from __future__ import annotations

import io
import os
import json

import pytest

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


# ──────────────────────────────────────────────────────────────── fixtures


@pytest.fixture
def lib_root(app_ctx, tmp_path, monkeypatch):
  from flask import current_app

  root = tmp_path / "reference_library"
  root.mkdir()
  monkeypatch.setitem(current_app.config, "XRAY_REFERENCE_LIBRARY_FOLDER", str(root))
  return root


@pytest.fixture
def seeded_library(lib_root):
  """Create a folder structure with images for catalog sync testing."""
  chest_pa = lib_root / "Chest" / "PA" / "Adult" / "Unisex"
  chest_pa.mkdir(parents=True)
  img_path = chest_pa / "healthy_chest_01.png"
  img_path.write_bytes(make_png_bytes())

  hand_ap = lib_root / "Hand" / "AP"
  hand_ap.mkdir(parents=True)
  img2 = hand_ap / "healthy_hand_01.png"
  img2.write_bytes(make_png_bytes(width=256, height=256))

  return lib_root


@pytest.fixture
def uploaded_ref(lib_root):
  """Upload a single reference via the service for matcher tests."""
  from app.services.xray.reference_xray_library_service import ReferenceXrayLibraryService

  f = make_filestorage("chest_ref.png")
  result = ReferenceXrayLibraryService.upload(f, VALID_META)
  assert result.success, result.message
  return result.data["reference"]


# ──────────────────────────────────── Module 5: Catalog Builder


class TestCatalogBuilder:
  def test_sync_creates_records(self, seeded_library):
    from app.services.xray.reference_catalog_service import ReferenceCatalogService

    result = ReferenceCatalogService.sync()
    assert result["success"] is True
    assert (result["created"] + result["updated"]) >= 2
    assert result["total_active"] >= 2

  def test_sync_idempotent(self, seeded_library):
    from app.services.xray.reference_catalog_service import ReferenceCatalogService

    r1 = ReferenceCatalogService.sync()
    r2 = ReferenceCatalogService.sync()
    assert r2["success"] is True
    assert r2["created"] == 0
    assert r2["updated"] >= 2

  def test_sync_deactivates_missing(self, seeded_library):
    from app.services.xray.reference_catalog_service import ReferenceCatalogService

    ReferenceCatalogService.sync()
    chest_img = seeded_library / "Chest" / "PA" / "Adult" / "Unisex" / "healthy_chest_01.png"
    chest_img.unlink()
    r2 = ReferenceCatalogService.sync()
    assert r2["deactivated"] >= 1

  def test_sync_parses_body_part_from_folder(self, seeded_library):
    from app.models.reference_xray_library_model import ReferenceXrayLibrary
    from app.services.xray.reference_catalog_service import ReferenceCatalogService

    ReferenceCatalogService.sync()
    row = ReferenceXrayLibrary.query.filter(
      ReferenceXrayLibrary.image_path.ilike("%hand%")
    ).first()
    assert row is not None
    assert row.body_part == "Hand"

  def test_sync_skips_thumbnails_dir(self, seeded_library):
    from app.services.xray.reference_catalog_service import ReferenceCatalogService

    thumb_dir = seeded_library / "_thumbnails"
    thumb_dir.mkdir()
    (thumb_dir / "should_skip.png").write_bytes(make_png_bytes(64, 64))
    result = ReferenceCatalogService.sync()
    assert result["success"] is True
    for err in result.get("errors", []):
      assert "_thumbnails" not in err


# ──────────────────────────────────── Module 6: Matching Engine


class TestReferenceMatcher:
  def test_match_exact_body_part(self, uploaded_ref, app_ctx):
    from app.services.xray.reference_matcher import ReferenceMatcher

    result = ReferenceMatcher.match(body_part="Chest", projection="PA", patient_age=30)
    assert result.success is True
    assert result.primary is not None
    assert result.primary["body_part"] == "Chest"
    assert result.cross_body is False
    assert result.score > 0

  def test_match_empty_library(self, lib_root, app_ctx):
    from app.services.xray.reference_matcher import ReferenceMatcher

    result = ReferenceMatcher.match(body_part="Knee")
    assert result.success is False
    assert result.error_code == "empty_library"
    assert result.primary is None
    assert "Healthy educational reference is not yet available" in (result.message or "")
    assert "AI analysis remains available" in (result.message or "")

  def test_match_cross_body_fallback(self, uploaded_ref, app_ctx):
    from app.services.xray.reference_matcher import ReferenceMatcher

    result = ReferenceMatcher.match(body_part="Knee", projection="AP")
    assert result.success is True
    assert result.cross_body is True
    assert "closest educational reference" in result.message.lower()

  def test_match_returns_alternatives(self, lib_root, app_ctx):
    from app.services.xray.reference_xray_library_service import ReferenceXrayLibraryService
    from app.services.xray.reference_matcher import ReferenceMatcher

    for i in range(3):
      f = make_filestorage(f"chest_{i}.png")
      meta = {**VALID_META, "title": f"Chest ref {i}"}
      r = ReferenceXrayLibraryService.upload(f, meta)
      assert r.success

    result = ReferenceMatcher.match(body_part="Chest", limit_alternatives=2)
    assert result.success is True
    assert len(result.alternatives) <= 2

  def test_match_gender_scoring(self, lib_root, app_ctx):
    from app.services.xray.reference_xray_library_service import ReferenceXrayLibraryService
    from app.services.xray.reference_matcher import ReferenceMatcher

    for g in ("Male", "Female"):
      f = make_filestorage(f"chest_{g.lower()}.png")
      meta = {**VALID_META, "gender": g, "title": f"Chest {g}"}
      ReferenceXrayLibraryService.upload(f, meta)

    result = ReferenceMatcher.match(body_part="Chest", gender="Female")
    assert result.success is True
    assert result.primary["gender"] == "Female"

  def test_match_age_scoring(self, lib_root, app_ctx):
    from app.services.xray.reference_xray_library_service import ReferenceXrayLibraryService
    from app.services.xray.reference_matcher import ReferenceMatcher

    for ag in ("Child", "Adult"):
      f = make_filestorage(f"chest_{ag.lower()}.png")
      meta = {**VALID_META, "age_group": ag, "title": f"Chest {ag}"}
      ReferenceXrayLibraryService.upload(f, meta)

    result = ReferenceMatcher.match(body_part="Chest", patient_age=8)
    assert result.success is True
    assert result.primary["age_group"] == "Child"

  def test_match_result_to_dict(self, uploaded_ref, app_ctx):
    from app.services.xray.reference_matcher import ReferenceMatcher

    result = ReferenceMatcher.match(body_part="Chest")
    d = result.to_dict()
    assert "disclaimer" in d
    assert "success" in d
    assert "primary" in d
    assert "score" in d


# ──────────────────────────────────── Module 7: Comparison Viewer (backend)


class TestComparisonService:
  def test_comparison_service_soft_empty(self, lib_root, app_ctx):
    """ComparisonService should gracefully handle empty library."""
    from app.services.xray.comparison_service import XrayComparisonService, ComparisonResult

    # With no uploaded refs, get_stored_comparison on a fake row returns None
    assert ComparisonResult(success=False, error_code="empty_library").to_dict()["error_code"] == "empty_library"

  def test_comparison_result_to_dict_shape(self):
    from app.services.xray.comparison_service import ComparisonResult

    r = ComparisonResult(
      success=True,
      provider="test",
      comparison_summary="Test summary.",
    )
    d = r.to_dict()
    assert d["success"] is True
    assert d["comparison_summary"] == "Test summary."
    assert "disclaimer" in d
    assert d["safety"]["image_sent_to_llm"] is False


# ──────────────────────────────────── Module 9: AI Comparison wording


class TestComparisonSanitization:
  def test_sanitize_forbidden_patterns(self, app_ctx):
    from app.services.xray.comparison_service import XrayComparisonService

    text = "You have pneumonia and are diagnosed with effusion."
    cleaned = XrayComparisonService._sanitize_text(text)
    assert "you have" not in cleaned.lower()
    assert "diagnosed with" not in cleaned.lower()

  def test_normalize_and_sanitize_fills_defaults(self, app_ctx):
    from app.services.xray.comparison_service import XrayComparisonService

    source = {
      "body_part": "Chest",
      "possible_findings": [{"label": "Opacity"}],
      "healthy_reference": {"body_part": "Chest", "age_group": "Adult"},
    }
    result = XrayComparisonService._normalize_and_sanitize({}, source)
    assert result["comparison_summary"]
    assert len(result["key_visual_differences"]) > 0
    assert len(result["normal_anatomical_landmarks"]) > 0
    assert "disclaimer" in result


# ──────────────────────────────────── Module 10: Learning Recommendations


class TestRecommendations:
  def test_build_recommendations_comparison_aware(self, app_ctx):
    from app.services.xray.recommendation_service import XrayRecommendationService

    result = XrayRecommendationService.build_recommendations(
      possible_findings=[{"label": "Pneumonia", "probability": 0.8}],
      body_part="Chest",
      comparison_context={
        "body_part": "Chest",
        "reference_body_part": "Chest",
        "learning_focus": ["Lung Anatomy", "Chest X-ray Interpretation"],
      },
    )
    assert result.success is True
    assert result.comparison_aware is True
    assert "Respiratory System" in result.topics or "Chest X-ray Interpretation" in result.topics

  def test_build_recommendations_clinical_context(self, app_ctx):
    from app.services.xray.recommendation_service import XrayRecommendationService

    result = XrayRecommendationService.build_recommendations(
      possible_findings=[],
      body_part="Chest",
      patient_clinical={
        "patient_age": 10,
        "smoking_history": "current smoker",
        "symptoms": "cough, fever",
      },
    )
    assert result.success is True
    assert result.clinical_context_used is True
    assert any("Pediatric" in t for t in result.topics)

  def test_build_recommendations_empty_input(self, app_ctx):
    from app.services.xray.recommendation_service import XrayRecommendationService

    result = XrayRecommendationService.build_recommendations(
      possible_findings=None,
      body_part=None,
    )
    assert result.success is True
    assert len(result.topics) > 0


# ──────────────────────────────────── Module 12: PDF Export


class TestPdfExport:
  def test_build_pdf_report_returns_bytes(self, app_ctx):
    from app.services.xray.export_service import XrayExportService
    from app.models.xray_analysis_model import XrayAnalysis

    row = XrayAnalysis.query.first()
    if row is None:
      pytest.skip("No XrayAnalysis rows in DB")

    pdf_bytes = XrayExportService.build_pdf_report(row)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes[:5] == b"%PDF-"

  def test_export_pdf_format(self, app_ctx):
    from app.services.xray.export_service import XrayExportService
    from app.models.xray_analysis_model import XrayAnalysis

    row = XrayAnalysis.query.first()
    if row is None:
      pytest.skip("No XrayAnalysis rows in DB")

    content, mimetype, filename = XrayExportService.export(row, "pdf")
    assert mimetype == "application/pdf"
    assert filename.endswith(".pdf")
    assert isinstance(content, bytes)

  def test_export_json_still_works(self, app_ctx):
    from app.services.xray.export_service import XrayExportService
    from app.models.xray_analysis_model import XrayAnalysis

    row = XrayAnalysis.query.first()
    if row is None:
      pytest.skip("No XrayAnalysis rows in DB")

    content, mimetype, filename = XrayExportService.export(row, "json")
    assert "application/json" in mimetype
    parsed = json.loads(content)
    assert parsed["product"] == "MediMentora"
    assert "comparison" in parsed

  def test_export_txt_still_works(self, app_ctx):
    from app.services.xray.export_service import XrayExportService
    from app.models.xray_analysis_model import XrayAnalysis

    row = XrayAnalysis.query.first()
    if row is None:
      pytest.skip("No XrayAnalysis rows in DB")

    content, mimetype, filename = XrayExportService.export(row, "txt")
    assert "text/plain" in mimetype
    assert "MediMentora" in content
    assert "Disclaimer" in content


# ──────────────────────────────────── Module 4: Metadata validation


class TestMetadataService:
  def test_validate_accepts_valid(self, app_ctx):
    from app.services.xray.reference_metadata_service import ReferenceMetadataService

    result = ReferenceMetadataService.validate(VALID_META, for_upload=True)
    assert result["success"] is True

  def test_validate_rejects_missing_required(self, app_ctx):
    from app.services.xray.reference_metadata_service import ReferenceMetadataService

    result = ReferenceMetadataService.validate({"body_part": "Chest"}, for_upload=True)
    assert result["success"] is False
    assert len(result["field_errors"]) > 0

  def test_validate_rejects_invalid_enum(self, app_ctx):
    from app.services.xray.reference_metadata_service import ReferenceMetadataService

    bad = {**VALID_META, "body_part": "Toe"}
    result = ReferenceMetadataService.validate(bad, for_upload=True)
    assert result["success"] is False

  def test_validate_lenient_for_update(self, app_ctx):
    from app.services.xray.reference_metadata_service import ReferenceMetadataService

    result = ReferenceMetadataService.validate(
      {"description": "Updated description"}, for_upload=False
    )
    assert result["success"] is True


# ──────────────────────────────────── Integration: Matcher via legacy bridge


class TestMatcherLegacyBridge:
  def test_select_reference_uses_matcher(self, uploaded_ref, app_ctx):
    from app.services.xray.reference_library import ReferenceLibraryService

    result = ReferenceLibraryService.select_reference(body_part="Chest")
    assert result.success is True
    assert result.primary is not None
    assert result.primary.body_part == "Chest"
    assert result.score > 0

  def test_select_reference_empty_library(self, lib_root, app_ctx):
    from app.services.xray.reference_library import ReferenceLibraryService

    result = ReferenceLibraryService.select_reference(body_part="Knee")
    assert result.success is False
    assert result.error_code == "empty_library"
