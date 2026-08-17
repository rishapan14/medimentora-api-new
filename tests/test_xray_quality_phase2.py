"""Phase 2 — image quality assessment tests."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from app.services.xray.quality import ImageQualityAssessor


def _write_png(path: str, arr: np.ndarray) -> str:
  import cv2

  ok = cv2.imwrite(path, arr)
  assert ok, "failed to write test png"
  return path


@pytest.fixture
def tmp_dir():
  with tempfile.TemporaryDirectory(prefix="xray_quality_") as d:
    yield d


def test_assess_good_synthetic_radiograph(tmp_dir):
  # Soft gradient + structure → should score reasonably (not camera/monitor)
  h, w = 512, 512
  yy, xx = np.mgrid[0:h, 0:w]
  base = (120 + 40 * np.sin(xx / 40.0) + 30 * np.cos(yy / 35.0)).astype(np.float32)
  noise = np.random.RandomState(0).normal(0, 2.0, size=(h, w))
  img = np.clip(base + noise, 0, 255).astype(np.uint8)
  path = _write_png(os.path.join(tmp_dir, "good.png"), img)

  result = ImageQualityAssessor().assess(path)
  assert result.success
  assert result.width == 512
  assert result.quality_score >= 55
  assert result.grade in ("excellent", "good", "fair", "poor")
  assert isinstance(result.to_dict()["issues"], list)


def test_assess_detects_low_resolution(tmp_dir):
  img = np.full((80, 80), 128, dtype=np.uint8)
  path = _write_png(os.path.join(tmp_dir, "tiny.png"), img)
  result = ImageQualityAssessor(min_ok_edge=256).assess(path)
  assert result.success
  assert any(i.code == "low_resolution" for i in result.issues)
  assert result.quality_score < 100
  assert result.suggestions


def test_assess_detects_blur(tmp_dir):
  import cv2

  rng = np.random.RandomState(1)
  sharp = rng.randint(40, 200, size=(400, 400), dtype=np.uint8)
  blurry = cv2.GaussianBlur(sharp, (31, 31), 0)
  path = _write_png(os.path.join(tmp_dir, "blur.png"), blurry)
  result = ImageQualityAssessor().assess(path)
  assert result.success
  assert any(i.code == "blur" for i in result.issues)


def test_assess_detects_under_exposure(tmp_dir):
  img = np.full((400, 400), 18, dtype=np.uint8)
  path = _write_png(os.path.join(tmp_dir, "dark.png"), img)
  result = ImageQualityAssessor().assess(path)
  assert result.success
  codes = {i.code for i in result.issues}
  assert "under_exposure" in codes or "low_contrast" in codes
  assert result.is_poor or result.quality_score < 70


def test_assess_detects_over_exposure(tmp_dir):
  img = np.full((400, 400), 245, dtype=np.uint8)
  path = _write_png(os.path.join(tmp_dir, "bright.png"), img)
  result = ImageQualityAssessor().assess(path)
  assert result.success
  codes = {i.code for i in result.issues}
  assert "over_exposure" in codes or "low_contrast" in codes


def test_assess_detects_color_camera_photo(tmp_dir):
  import cv2

  # Strong chromatic channels → camera photo heuristic
  bgr = np.zeros((400, 400, 3), dtype=np.uint8)
  bgr[:, :, 0] = 40
  bgr[:, :, 1] = 120
  bgr[:, :, 2] = 200
  path = os.path.join(tmp_dir, "color.jpg")
  cv2.imwrite(path, bgr)
  result = ImageQualityAssessor().assess(path)
  assert result.success
  assert any(i.code == "camera_photo" for i in result.issues)


def test_assess_missing_file():
  result = ImageQualityAssessor().assess(os.path.join("no", "such", "file.png"))
  assert not result.success
  assert result.error_code == "missing_file"
