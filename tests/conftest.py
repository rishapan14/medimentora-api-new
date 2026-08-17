"""Shared fixtures for MediMentora X-ray tests (Module 11)."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from werkzeug.datastructures import FileStorage

# Ensure medimentor-api root is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

os.environ.setdefault("FLASK_DEBUG", "false")


def make_png_bytes(width: int = 320, height: int = 320, asymmetric: bool = True) -> bytes:
  """Build an in-memory grayscale PNG with random salt so content hash is unique per call."""
  import random
  salt = random.randint(0, 255)
  img = Image.new("L", (width, height), color=max(1, (40 + salt) % 256))
  draw = ImageDraw.Draw(img)
  # Scatter a few random pixels to guarantee unique content hash
  for _ in range(20):
    px = random.randint(0, max(0, width - 1))
    py = random.randint(0, max(0, height - 1))
    img.putpixel((px, py), random.randint(0, 255))
  if width >= 64 and height >= 64:
    if asymmetric:
      draw.ellipse((20, 30, max(30, width // 2 - 10), height - 30), fill=90)
      draw.ellipse((min(width - 30, width // 2 + 10), 30, width - 20, height - 30), fill=170)
      draw.ellipse((width // 3, height // 3, 2 * width // 3, 2 * height // 3), fill=200)
    else:
      draw.ellipse((40, 40, width - 40, height - 40), fill=120)
  else:
    # Tiny images used for resolution rejection tests
    draw.rectangle((0, 0, width - 1, height - 1), fill=90)
  buf = io.BytesIO()
  img.save(buf, format="PNG")
  return buf.getvalue()


def make_filestorage(
  filename: str = "chest.png",
  *,
  asymmetric: bool = True,
  width: int = 320,
  height: int = 320,
  content_type: str = "image/png",
) -> FileStorage:
  raw = make_png_bytes(width=width, height=height, asymmetric=asymmetric)
  return FileStorage(
    stream=io.BytesIO(raw),
    filename=filename,
    content_type=content_type,
  )


@pytest.fixture
def png_bytes():
  return make_png_bytes()


@pytest.fixture
def png_file():
  return make_filestorage()


@pytest.fixture(scope="session")
def app():
  """Flask app for integration tests (requires MySQL)."""
  try:
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application
  except Exception as exc:  # pragma: no cover
    pytest.skip(f"App unavailable for integration tests: {exc}")


@pytest.fixture
def app_ctx(app):
  with app.app_context():
    yield app


@pytest.fixture
def client(app):
  return app.test_client()


@pytest.fixture
def auth_headers(client, app):
  """JWT headers for demo student account (skips if login fails)."""
  response = client.post(
    "/api/auth/login",
    json={"email": "student@clinical.com", "password": "student123"},
  )
  if response.status_code != 200:
    pytest.skip(f"Demo login unavailable ({response.status_code})")
  payload = response.get_json() or {}
  data = payload.get("data") or {}
  token = data.get("access_token")
  if not token:
    pytest.skip("No access token returned from login")
  return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers(client, app):
  """JWT headers for demo admin account (skips if login fails)."""
  response = client.post(
    "/api/auth/login",
    json={"email": "admin@clinical.com", "password": "admin123"},
  )
  if response.status_code != 200:
    pytest.skip(f"Admin login unavailable ({response.status_code})")
  payload = response.get_json() or {}
  data = payload.get("data") or {}
  token = data.get("access_token")
  if not token:
    pytest.skip("No admin access token returned from login")
  user = data.get("user") or {}
  if (user.get("role") or "").lower() != "admin" and not user.get("is_admin"):
    pytest.skip("Logged-in account is not admin")
  return {"Authorization": f"Bearer {token}"}
