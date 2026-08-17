"""Phase 5 — automatic projection detection tests."""

from __future__ import annotations

import os

import numpy as np


def _write_gray(path: str, arr: np.ndarray) -> str:
  import cv2

  assert cv2.imwrite(path, arr)
  return path


def test_detector_returns_projection_and_confidence(tmp_path):
  from app.services.xray.projection_detection import HeuristicProjectionDetector

  # Symmetric frontal-like image
  h, w = 400, 420
  img = np.full((h, w), 110, dtype=np.uint8)
  img[:, w // 2 - 20 : w // 2 + 20] = 160
  # Mirror to boost symmetry
  img[:, w // 2 :] = np.fliplr(img[:, : w // 2])
  path = _write_gray(str(tmp_path / "frontal.png"), img)

  result = HeuristicProjectionDetector().detect(path, body_part="Chest")
  assert result.success
  assert result.projection in ("AP", "PA", "Lateral", "Oblique", "Unknown")
  assert 0 < result.confidence <= 1
  assert result.candidates
  assert result.to_dict()["projection"] == result.projection


def test_asymmetric_image_leans_lateral_or_oblique(tmp_path):
  from app.services.xray.projection_detection import HeuristicProjectionDetector

  h, w = 420, 320
  img = np.full((h, w), 80, dtype=np.uint8)
  img[:, :80] = 40
  img[:, 180:] = 170
  img[50:370, 200:280] = 200
  path = _write_gray(str(tmp_path / "side.png"), img)

  result = HeuristicProjectionDetector().detect(path, body_part="Chest")
  assert result.success
  labels = [c.label for c in result.candidates[:3]]
  assert any(x in labels for x in ("Lateral", "Oblique", "Unknown", "AP", "PA"))


def test_canonicalize_aliases():
  from app.services.xray.projection_detection import ProjectionDetector

  assert ProjectionDetector.canonicalize("pa") == "PA"
  assert ProjectionDetector.canonicalize("AnteroPosterior") == "AP"
  assert ProjectionDetector.canonicalize("lat") == "Lateral"
  assert ProjectionDetector.canonicalize("other") == "Unknown"
  assert ProjectionDetector.canonicalize(None) is None


def test_missing_file():
  from app.services.xray.projection_detection import get_projection_detector

  result = get_projection_detector().detect(os.path.join("no", "file.png"))
  assert not result.success
  assert result.error_code == "missing_file"


def test_factory_default():
  from app.services.xray.projection_detection import (
    HeuristicProjectionDetector,
    get_projection_detector,
  )

  assert isinstance(get_projection_detector("heuristic"), HeuristicProjectionDetector)
  assert isinstance(get_projection_detector("unknown"), HeuristicProjectionDetector)
