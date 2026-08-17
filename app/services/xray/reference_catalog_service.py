"""Automatic Reference Catalog Builder (Module 5).

Scans the library folder tree, extracts image metadata, generates thumbnails,
upserts DB rows, and deactivates records whose files disappeared — all without
manual rebuilding.

Folder convention (all segments optional — parser fills defaults):
  reference_library/{body_part}/{projection}/{age_group}/{gender}/{orientation}/{file}

Call ``ReferenceCatalogService.sync()`` from an admin endpoint, CLI script, or
startup hook. The operation is idempotent and safe to run concurrently
(last writer wins on a per-file basis).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any

from app.extensions import db
from app.models.reference_xray_library_model import (
  REFERENCE_AGE_GROUPS,
  REFERENCE_BODY_PARTS,
  REFERENCE_GENDERS,
  REFERENCE_ORIENTATIONS,
  REFERENCE_PROJECTIONS,
  ReferenceXrayLibrary,
)
from app.services.xray.reference_xray_library_service import (
  IMAGE_EXTENSIONS,
  ReferenceXrayLibraryService,
)
from app.utils import utc_now

logger = logging.getLogger(__name__)


def _normalize_segment(raw: str, allowed: tuple[str, ...], default: str) -> str:
  """Case-insensitive match of a folder segment against an allowed set."""
  cleaned = raw.strip().replace("_", " ").replace("-", " ")
  lookup = {a.lower(): a for a in allowed}
  return lookup.get(cleaned.lower(), default)


class ReferenceCatalogService:
  """Scan disk → extract metadata → thumbnails → DB upsert.  Zero manual steps."""

  @classmethod
  def sync(cls, *, uploaded_by: int | None = None) -> dict[str, Any]:
    """Full idempotent sync of the library folder into ``reference_xray_library``.

    Returns a summary dict with counts of created / updated / skipped /
    deactivated rows.
    """
    root = ReferenceXrayLibraryService.ensure_root()
    created = 0
    updated = 0
    skipped = 0
    deactivated = 0
    errors: list[str] = []

    try:
      seen_paths: set[str] = set()

      for dirpath, _dirs, filenames in os.walk(root):
        # Skip internal dirs like _thumbnails
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        if rel_dir.startswith("_"):
          continue

        for name in filenames:
          ext = os.path.splitext(name)[1].lower()
          if ext not in IMAGE_EXTENSIONS:
            continue

          abs_path = os.path.join(dirpath, name)
          rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
          seen_paths.add(rel_path)

          segments = rel_path.split("/")
          taxonomy = cls._parse_segments(segments)

          try:
            existing = ReferenceXrayLibrary.query.filter_by(image_path=rel_path).first()

            image_meta = ReferenceXrayLibraryService._read_image_metadata(abs_path)

            if existing:
              # Update metadata from disk structure + re-read dimensions
              cls._apply_taxonomy(existing, taxonomy)
              existing.mime_type = image_meta.get("mime_type")
              existing.file_size = image_meta.get("file_size")
              existing.width = image_meta.get("width")
              existing.height = image_meta.get("height")
              existing.content_hash = image_meta.get("content_hash")
              existing.is_active = True
              existing.updated_at = utc_now()
              # Re-generate thumbnail if missing
              if not existing.thumbnail_path or not os.path.isfile(
                os.path.join(root, (existing.thumbnail_path or "").replace("\\", "/"))
              ):
                existing.thumbnail_path = ReferenceXrayLibraryService._generate_thumbnail(
                  abs_path,
                  existing.public_id or f"sync_{existing.id}",
                  ext,
                )
              updated += 1
            else:
              public_id = f"ref_{uuid.uuid4().hex[:16]}"
              thumb_rel = ReferenceXrayLibraryService._generate_thumbnail(
                abs_path, public_id, ext
              )
              row = ReferenceXrayLibrary(
                title=taxonomy["title"],
                body_part=taxonomy["body_part"],
                projection=taxonomy["projection"],
                orientation=taxonomy["orientation"],
                age_group=taxonomy["age_group"],
                gender=taxonomy["gender"],
                image_path=rel_path,
                thumbnail_path=thumb_rel,
                source=taxonomy.get("source") or "Disk sync",
                license=taxonomy.get("license") or "",
                description=taxonomy.get("description")
                or f"Healthy {taxonomy['body_part']} {taxonomy['projection']} reference.",
                anatomical_notes=taxonomy.get("anatomical_notes") or "",
                difficulty=taxonomy.get("difficulty") or "Beginner",
                is_active=True,
                uploaded_by=uploaded_by,
                public_id=public_id,
                mime_type=image_meta.get("mime_type"),
                file_size=image_meta.get("file_size"),
                width=image_meta.get("width"),
                height=image_meta.get("height"),
                content_hash=image_meta.get("content_hash"),
              )
              db.session.add(row)
              created += 1

          except Exception as exc:
            skipped += 1
            errors.append(f"{rel_path}: {exc}")
            logger.exception("Catalog sync error for %s", rel_path)
            db.session.rollback()
            continue

      # Deactivate DB rows whose files no longer exist on disk
      active_rows = ReferenceXrayLibrary.query.filter_by(is_active=True).all()
      for row in active_rows:
        if row.image_path and row.image_path not in seen_paths:
          abs_check = os.path.join(root, row.image_path.replace("\\", "/"))
          if not os.path.isfile(abs_check):
            row.is_active = False
            row.updated_at = utc_now()
            deactivated += 1
            logger.info(
              "Deactivated missing reference id=%s path=%s", row.id, row.image_path
            )

      db.session.commit()

      total_active = ReferenceXrayLibraryService.count(active_only=True)
      total_all = ReferenceXrayLibraryService.count(active_only=False)

      summary = {
        "success": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "deactivated": deactivated,
        "total_active": total_active,
        "total_all": total_all,
        "library_root": root,
        "errors": errors[:20],
      }
      logger.info(
        "Catalog sync complete: created=%d updated=%d skipped=%d deactivated=%d "
        "total_active=%d",
        created,
        updated,
        skipped,
        deactivated,
        total_active,
      )
      return summary

    except Exception as exc:
      db.session.rollback()
      logger.exception("Catalog sync failed globally")
      return {
        "success": False,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "deactivated": deactivated,
        "error": str(exc),
        "errors": errors[:20],
      }

  # ------------------------------------------------------------------ parsing

  @classmethod
  def _parse_segments(cls, segments: list[str]) -> dict[str, str]:
    """Extract taxonomy from folder path segments.

    Expected:  body_part / projection / age_group / gender / orientation / filename
    Shorter paths fill defaults from the right.
    """
    parts = [s.strip() for s in segments if s.strip()]
    filename = parts[-1] if parts else "unknown.png"
    dirs = parts[:-1]

    body = _normalize_segment(dirs[0], REFERENCE_BODY_PARTS, "Other") if len(dirs) >= 1 else "Other"
    projection = _normalize_segment(dirs[1], REFERENCE_PROJECTIONS, "Other") if len(dirs) >= 2 else "Other"
    age = _normalize_segment(dirs[2], REFERENCE_AGE_GROUPS, "Adult") if len(dirs) >= 3 else "Adult"
    gender = _normalize_segment(dirs[3], REFERENCE_GENDERS, "Unisex") if len(dirs) >= 4 else "Unisex"
    orientation = _normalize_segment(dirs[4], REFERENCE_ORIENTATIONS, "Unknown") if len(dirs) >= 5 else "Unknown"

    stem = os.path.splitext(filename)[0]
    title = f"Healthy {body} {projection} reference ({age}, {gender})"

    return {
      "body_part": body,
      "projection": projection,
      "orientation": orientation,
      "age_group": age,
      "gender": gender,
      "title": title,
      "source": "Disk sync",
      "license": "",
      "description": f"Healthy {body} {projection} reference.",
      "anatomical_notes": "",
      "difficulty": "Beginner",
    }

  @staticmethod
  def _apply_taxonomy(row: ReferenceXrayLibrary, taxonomy: dict[str, str]) -> None:
    """Update taxonomy fields on an existing row from parsed folder structure."""
    row.body_part = taxonomy["body_part"]
    row.projection = taxonomy["projection"]
    row.orientation = taxonomy["orientation"]
    row.age_group = taxonomy["age_group"]
    row.gender = taxonomy["gender"]
    if not row.title or row.title.startswith("Healthy "):
      row.title = taxonomy["title"]
    if not row.description:
      row.description = taxonomy.get("description") or ""
    if not row.source:
      row.source = taxonomy.get("source") or "Disk sync"
