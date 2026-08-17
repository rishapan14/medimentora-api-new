"""Phase 4 — automatic body-part detection tests."""

from __future__ import annotations

import os

import numpy as np
import pytest


def _write_gray(path: str, arr: np.ndarray) -> str:
  import cv2

  assert cv2.imwrite(path, arr)
  return path


def test_detector_returns_label_and_confidence(tmp_path):
  from app.services.xray.body_detection import HeuristicBodyPartDetector

  # Synthetic "chest-like": mid brighter than sides
  h, w = 400, 420
  img = np.full((h, w), 90, dtype=np.uint8)
  img[:, : w // 3] = 55
  img[:, 2 * w // 3 :] = 55
  img[:, w // 3 : 2 * w // 3] = 140
  path = _write_gray(str(tmp_path / "chest.png"), img)

  result = HeuristicBodyPartDetector().detect(path)
  assert result.success
  assert result.body_part in (
    "Chest",
    "Hand",
    "Leg",
    "Foot",
    "Spine",
    "Shoulder",
    "Pelvis",
    "Dental",
    "Knee",
  )
  assert 0 < result.confidence <= 1
  assert result.candidates
  assert result.to_dict()["body_part"] == result.body_part


def test_detector_tall_image_prefers_vertical_parts(tmp_path):
  from app.services.xray.body_detection import HeuristicBodyPartDetector

  # Tall column — spine/leg family
  img = np.full((500, 220), 110, dtype=np.uint8)
  img[:, 90:130] = 180
  path = _write_gray(str(tmp_path / "tall.png"), img)
  result = HeuristicBodyPartDetector().detect(path)
  assert result.success
  assert result.body_part in ("Spine", "Leg", "Knee", "Chest", "Hand", "Shoulder", "Pelvis", "Foot", "Dental")
  labels = [c.label for c in result.candidates[:3]]
  assert any(x in labels for x in ("Spine", "Leg"))


def test_canonicalize_aliases():
  from app.services.xray.body_detection import BodyPartDetector

  assert BodyPartDetector.canonicalize("wrist") == "Hand"
  assert BodyPartDetector.canonicalize("Hip") == "Pelvis"
  assert BodyPartDetector.canonicalize("Chest") == "Chest"
  assert BodyPartDetector.canonicalize(None) is None


def test_missing_file():
  from app.services.xray.body_detection import get_detector

  result = get_detector().detect(os.path.join("no", "file.png"))
  assert not result.success
  assert result.error_code == "missing_file"


def test_factory_default():
  from app.services.xray.body_detection import HeuristicBodyPartDetector, get_detector

  assert isinstance(get_detector("heuristic"), HeuristicBodyPartDetector)
  assert isinstance(get_detector("unknown-model"), HeuristicBodyPartDetector)
