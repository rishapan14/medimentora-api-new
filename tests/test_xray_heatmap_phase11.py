"""Phase 11 — Grad-CAM / attention heatmap package tests."""

from __future__ import annotations

import os
import tempfile

import pytest

from app.services.xray.heatmap import (
  HEATMAP_METHOD_GRADCAM_PROXY,
  HEATMAP_METHOD_HEURISTIC,
  HeatmapService,
  generate_gradcam_proxy,
  highlight_regions_from_findings,
  try_gradcam,
)
from tests.conftest import make_png_bytes


@pytest.fixture
def temp_png_path():
  raw = make_png_bytes(asymmetric=True)
  fd, path = tempfile.mkstemp(suffix=".png")
  os.close(fd)
  with open(path, "wb") as f:
    f.write(raw)
  yield path
  try:
    os.remove(path)
  except OSError:
    pass


def test_gradcam_proxy_generation(temp_png_path, app_ctx):
  result = generate_gradcam_proxy(
    temp_png_path,
    xray_id=999011,
    findings=[
      {
        "label": "Possible Lung Opacity",
        "probability": 0.82,
        "region": "asymmetric_lung_zone",
      },
      {
        "label": "Possible Cardiomegaly",
        "probability": 0.55,
        "region": "cardiac_silhouette",
      },
    ],
    body_part="Chest",
  )
  assert result.success
  assert result.method == HEATMAP_METHOD_GRADCAM_PROXY
  assert result.heatmap_path and os.path.isfile(result.heatmap_path)
  assert result.overlay_path and os.path.isfile(result.overlay_path)
  meta = result.meta_for_storage()
  assert meta["method"] == HEATMAP_METHOD_GRADCAM_PROXY
  assert isinstance(meta["highlighted_regions"], list)
  assert len(meta["highlighted_regions"]) >= 1
  safety = result.to_dict()["safety"]
  assert safety["is_gradcam_proxy"] is True
  assert safety["gradcam_family"] is True
  assert safety["educational_only"] is True
  for p in (result.heatmap_path, result.overlay_path):
    if p and os.path.isfile(p):
      os.remove(p)


def test_prefer_gradcam_uses_proxy(temp_png_path, app_ctx):
  result = HeatmapService.generate(
    temp_png_path,
    xray_id=999012,
    findings=[{"label": "Possible Fracture", "probability": 0.7, "region": "center"}],
    body_part="Hand",
    prefer_gradcam=True,
  )
  assert result.success
  assert result.method == HEATMAP_METHOD_GRADCAM_PROXY
  for p in (result.heatmap_path, result.overlay_path):
    if p and os.path.isfile(p):
      os.remove(p)


def test_prefer_gradcam_false_uses_heuristic(temp_png_path, app_ctx):
  result = HeatmapService.generate(
    temp_png_path,
    xray_id=999013,
    findings=[{"label": "Possible Fracture", "probability": 0.7, "region": "center"}],
    prefer_gradcam=False,
  )
  assert result.success
  assert result.method == HEATMAP_METHOD_HEURISTIC
  for p in (result.heatmap_path, result.overlay_path):
    if p and os.path.isfile(p):
      os.remove(p)


def test_try_gradcam_returns_proxy(temp_png_path, app_ctx):
  result = try_gradcam(
    temp_png_path,
    xray_id=999014,
    findings=[{"label": "Possible Pneumonia", "probability": 0.6, "region": "lower_lung_zones"}],
  )
  assert result is not None
  assert result.success
  assert result.method == HEATMAP_METHOD_GRADCAM_PROXY
  for p in (result.heatmap_path, result.overlay_path):
    if p and os.path.isfile(p):
      os.remove(p)


def test_highlight_regions_boxes():
  regions = highlight_regions_from_findings(
    [
      {"label": "Possible Lung Opacity", "probability": 0.8, "region": "upper_left"},
      {"label": "Possible Cardiomegaly", "probability": 0.5, "region": "cardiac_silhouette"},
    ],
    height=200,
    width=200,
  )
  assert len(regions) == 2
  for r in regions:
    assert "box_pct" in r
    assert 0 <= r["confidence"] <= 1
    box = r["box_pct"]
    assert "x" in box and "y" in box and "w" in box and "h" in box
