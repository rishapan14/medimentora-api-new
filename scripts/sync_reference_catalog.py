"""Scan reference_library folder and sync images into the database.

Usage (from medimentor-api):
  .\.venv\Scripts\python.exe scripts/sync_reference_catalog.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


def main() -> int:
  from app import create_app
  from app.services.xray.reference_catalog_service import ReferenceCatalogService

  app = create_app()
  with app.app_context():
    result = ReferenceCatalogService.sync()
    print(json.dumps(result, indent=2, default=str))
  return 0 if result.get("success") else 1


if __name__ == "__main__":
  raise SystemExit(main())
