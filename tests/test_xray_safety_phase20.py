"""Phase 20 — educational safety wording tests."""

from __future__ import annotations

from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER, XRAY_SHORT_DISCLAIMER
from app.services.xray.safety_wording import (
  ensure_short_disclaimer,
  hedge_finding_label,
  sanitize_educational_text,
)


def test_short_disclaimer_exact_phase20_text():
  assert XRAY_SHORT_DISCLAIMER == (
    "For educational purposes only. This is not a diagnosis. "
    "Please consult a qualified healthcare professional."
  )
  assert XRAY_SHORT_DISCLAIMER in XRAY_MEDICAL_DISCLAIMER
  assert "not a diagnosis" in XRAY_MEDICAL_DISCLAIMER.lower()


def test_hedge_finding_label_never_says_you_have():
  phrased = hedge_finding_label("Possible Pneumonia")
  assert "you have" not in phrased.lower()
  assert "may be consistent with pneumonia" in phrased.lower()
  assert phrased.startswith("The AI detected findings")


def test_sanitize_rewrites_definitive_claims():
  cleaned = sanitize_educational_text("You have pneumonia.")
  assert "you have" not in cleaned.lower()
  assert "may be consistent with pneumonia" in cleaned.lower()


def test_ensure_short_disclaimer_prepends():
  out = ensure_short_disclaimer("Extra clinical detail.")
  assert out.startswith(XRAY_SHORT_DISCLAIMER)
  assert "Extra clinical detail." in out


def test_openapi_meta_includes_short_disclaimer(client):
  response = client.get("/apispec/xray")
  assert response.status_code == 200
  data = response.get_json()["data"]
  assert data["short_disclaimer"] == XRAY_SHORT_DISCLAIMER
  assert "consult a qualified healthcare professional" in data["short_disclaimer"].lower()
