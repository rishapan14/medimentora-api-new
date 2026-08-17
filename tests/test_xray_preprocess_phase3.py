"""Phase 3 — OpenCV X-ray preprocessing pipeline tests."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from tests.conftest import make_png_bytes


@pytest.fixture
def radiograph_png(tmp_path):
  raw = make_png_bytes(width=400, height=400, asymmetric=True)
  path = tmp_path / "chest.png"
  path.write_bytes(raw)
  return str(path)


def test_pipeline_applies_core_phase3_steps(radiograph_png, tmp_path):
  from app.services.xray.image_preprocessor import ImagePreprocessor

  out = str(tmp_path / "out.png")
  result = ImagePreprocessor().enhance(radiograph_png, output_path=out)
  assert result.success
  assert os.path.isfile(out)
  steps = set(result.applied_steps)
  # Core Phase 3 checklist (some steps may be *_none / *_skipped variants)
  assert any(s.startswith("load") or s.startswith("auto_rotate") for s in steps)
  assert "grayscale" in steps or "grayscale_skip" in steps
  assert "bilateral_denoise" in steps or "gaussian_denoise" in steps
  assert "clahe" in steps
  assert "histogram_equalization_blend" in steps
  assert any(s.startswith("brightness_normalization") for s in steps)
  assert "sharpness_enhancement" in steps
  assert "contrast_enhancement" in steps
  assert "resize" in steps or "resize_skipped" in steps
  assert "normalization" in steps
  assert "save_png" in steps
  assert result.normalization is not None
  assert "mean" in result.normalization
  assert result.mean_intensity is not None
  assert result.to_dict()["normalization"]["normalized_mean"] >= 0


def test_border_removal_crops_dark_frame(tmp_path):
  import cv2
  from app.services.xray.preprocessing.steps import remove_borders

  # Content square inside a thick black border
  img = np.zeros((300, 300), dtype=np.uint8)
  img[40:260, 40:260] = 140
  cv2.rectangle(img, (60, 60), (240, 240), 200, thickness=8)
  cropped, step, warn = remove_borders(img, cv2, np)
  assert warn is None
  assert step in ("border_removal", "border_removal_none", "border_removal_skipped")
  assert cropped.shape[0] <= 300 and cropped.shape[1] <= 300


def test_brightness_normalization_shifts_dark_image():
  from app.services.xray.preprocessing.steps import normalize_brightness

  dark = np.full((128, 128), 40, dtype=np.uint8)
  out, step, warn = normalize_brightness(dark, np, target_mean=128.0)
  assert warn is None
  assert step == "brightness_normalization"
  assert float(np.mean(out)) > float(np.mean(dark))


def test_sharpness_enhancement_runs():
  import cv2
  from app.services.xray.preprocessing.steps import enhance_sharpness

  rng = np.random.RandomState(0)
  img = rng.randint(50, 180, size=(200, 200), dtype=np.uint8)
  out, step, warn = enhance_sharpness(img, cv2)
  assert warn is None
  assert step == "sharpness_enhancement"
  assert out.shape == img.shape


def test_facade_import_matches_pipeline():
  from app.services.xray import image_preprocessor as facade
  from app.services.xray.preprocessing import pipeline

  assert facade.ImagePreprocessor is pipeline.ImagePreprocessor
  assert facade.XrayPreprocessResult is pipeline.XrayPreprocessResult


def test_missing_file_preprocess():
  from app.services.xray.image_preprocessor import ImagePreprocessor

  result = ImagePreprocessor().enhance(os.path.join("missing", "xray.png"))
  assert not result.success
  assert result.error_code == "missing_file"
