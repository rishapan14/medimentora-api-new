"""Educational healthy X-ray reference library (real radiographs only).

Organization on disk:
  reference_library/
    {body_part}/{projection}/{age_group}/{gender}/{id}.{jpg|jpeg|png|webp}

Matching prefers body part + projection + age group, and gender only when
clinically relevant for that body part. No placeholder drawings or icons.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from flask import current_app, has_app_context

from app.models.xray_analysis_model import (
  XRAY_AGE_GROUPS,
  XRAY_BODY_PARTS,
  XRAY_GENDER_RELEVANT_BODY_PARTS,
  XRAY_MEDICAL_DISCLAIMER,
  XRAY_PROJECTIONS,
  XRAY_REFERENCE_GENDERS,
)

from app.services.xray.reference_xray_library_service import EMPTY_LIBRARY_MESSAGE

logger = logging.getLogger(__name__)

CATALOG_FILENAME = "catalog.json"
CATALOG_VERSION = "2.0.0"
CHILD_AGE_MAX = 17  # legacy ceiling for Child/Teen band (see age_group_from_age)
INFANT_AGE_MAX = 1
CHILD_BAND_MAX = 12
TEEN_AGE_MAX = 17
ADULT_AGE_MAX = 64

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")

# Reject known synthetic / placeholder markers
PLACEHOLDER_MARKERS = (
  "synthetic educational placeholder",
  "not a real patient image",
  "placeholder",
  "educational healthy reference placeholder",
  "_write_placeholder",
)


@dataclass
class ReferenceImage:
  """One educational healthy reference radiograph entry."""

  id: str
  body_part: str
  projection: str
  age_group: str
  gender: str
  relative_path: str
  absolute_path: str
  label: str = "Educational healthy reference"
  notes: str = ""
  license: str = ""
  source: str = ""
  gender_relevant: bool = False

  def to_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "body_part": self.body_part,
      "projection": self.projection,
      "age_group": self.age_group,
      "gender": self.gender,
      "relative_path": self.relative_path,
      "path": self.absolute_path,
      "label": self.label,
      "notes": self.notes,
      "license": self.license,
      "source": self.source,
      "gender_relevant": self.gender_relevant,
      "exists": os.path.isfile(self.absolute_path),
      "mime_type": self.mime_type(),
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "healthy_reference": True,
        "real_radiograph_required": True,
      },
    }

  def mime_type(self) -> str:
    ext = os.path.splitext(self.absolute_path)[1].lower()
    return {
      ".png": "image/png",
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".webp": "image/webp",
      ".tif": "image/tiff",
      ".tiff": "image/tiff",
    }.get(ext, "application/octet-stream")


@dataclass
class ReferenceSelectionResult:
  success: bool
  primary: ReferenceImage | None = None
  alternatives: list[ReferenceImage] = field(default_factory=list)
  matched_age_group: str | None = None
  matched_body_part: str | None = None
  matched_projection: str | None = None
  gender_used: bool = False
  score: int = 0
  message: str = ""
  error_code: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "success": self.success,
      "primary": self.primary.to_dict() if self.primary else None,
      "alternatives": [a.to_dict() for a in self.alternatives],
      "matched_age_group": self.matched_age_group,
      "matched_body_part": self.matched_body_part,
      "matched_projection": self.matched_projection,
      "gender_used": self.gender_used,
      "score": self.score,
      "message": self.message,
      "error_code": self.error_code,
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    }


class ReferenceLibraryService:
  """Catalog + select real healthy educational reference X-rays."""

  @classmethod
  def library_root(cls) -> str:
    if has_app_context():
      root = current_app.config.get("XRAY_REFERENCE_LIBRARY_FOLDER")
      if root:
        return str(root)
    return os.path.abspath(
      os.path.join(os.path.dirname(__file__), "..", "..", "..", "reference_library")
    )

  @classmethod
  def catalog_path(cls) -> str:
    return os.path.join(cls.library_root(), CATALOG_FILENAME)

  @classmethod
  def ensure_library(cls, force_resync: bool = False) -> str:
    """Ensure library folder exists and catalog is loaded/synced from disk."""
    root = cls.library_root()
    os.makedirs(root, exist_ok=True)
    catalog = cls.catalog_path()
    if force_resync or not os.path.isfile(catalog) or cls._catalog_empty():
      # Prefer rebuilding from real image files on disk over inventing placeholders
      rebuilt = cls.rebuild_catalog_from_disk()
      if rebuilt.get("references"):
        return root
      # Keep an empty catalog template (never seed drawings)
      if not os.path.isfile(catalog):
        cls._write_catalog([])
    return root

  @classmethod
  def _catalog_empty(cls) -> bool:
    try:
      with open(cls.catalog_path(), encoding="utf-8") as f:
        data = json.load(f)
      refs = data.get("references") or []
      # Treat placeholder-only catalogs as empty for real-image mode
      real = [r for r in refs if not cls._looks_like_placeholder_entry(r)]
      return len(real) == 0
    except Exception:
      return True

  @staticmethod
  def _looks_like_placeholder_entry(item: dict[str, Any]) -> bool:
    blob = " ".join(
      str(item.get(k) or "") for k in ("notes", "label", "source", "license", "id")
    ).lower()
    return any(marker in blob for marker in PLACEHOLDER_MARKERS)

  @classmethod
  def rebuild_catalog_from_disk(cls) -> dict[str, Any]:
    """
    Walk body_part/projection/age_group/gender folders and write catalog.json.

    Drop images that look like legacy placeholder drawings (by path/notes).
    """
    root = cls.library_root()
    os.makedirs(root, exist_ok=True)
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for dirpath, _dirnames, filenames in os.walk(root):
      for name in filenames:
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
          continue
        abs_path = os.path.join(dirpath, name)
        rel = os.path.relpath(abs_path, root).replace("\\", "/")
        parts = rel.split("/")
        # Expected: body/projection/age/gender/file
        if len(parts) < 5:
          logger.warning("Skipping reference outside taxonomy folders: %s", rel)
          continue
        body_raw, proj_raw, age_raw, gender_raw = parts[0], parts[1], parts[2], parts[3]
        body = cls.normalize_body_part(body_raw.replace("_", " "))
        projection = cls.normalize_projection(proj_raw) or "Other"
        age = cls.normalize_age_group(age_raw) or "Adult"
        gender = cls.normalize_gender(gender_raw) or "Unisex"
        stem = os.path.splitext(parts[-1])[0]
        ref_id = re.sub(r"[^a-zA-Z0-9_\-]+", "_", stem).strip("_").lower() or rel.replace("/", "_")
        if ref_id in seen_ids:
          ref_id = f"{ref_id}_{len(seen_ids)}"
        seen_ids.add(ref_id)

        # Skip obvious legacy placeholder filenames
        if "placeholder" in rel.lower() or "unisex_01" in rel.lower() and "healthy" not in rel.lower():
          # Still allow real files; only skip if directory was from old seed layout without projection
          if len(parts) == 4:  # old layout body/age/gender/file
            continue

        entry = {
          "id": ref_id,
          "body_part": body,
          "projection": projection,
          "age_group": age,
          "gender": gender,
          "relative_path": rel,
          "label": f"Healthy {body} {projection} reference ({age}, {gender})",
          "notes": "Real educational healthy radiograph for teaching comparison only.",
          "license": "",
          "source": "",
          "gender_relevant": body in XRAY_GENDER_RELEVANT_BODY_PARTS,
        }
        if cls._looks_like_placeholder_entry(entry) and "placeholder" in rel.lower():
          continue
        entries.append(entry)

    # Merge any manually curated catalog entries that point at existing files
    existing_manual: list[dict[str, Any]] = []
    if os.path.isfile(cls.catalog_path()):
      try:
        with open(cls.catalog_path(), encoding="utf-8") as f:
          prior = json.load(f)
        for item in prior.get("references") or []:
          if cls._looks_like_placeholder_entry(item):
            continue
          rel = str(item.get("relative_path") or "").replace("\\", "/")
          abs_path = os.path.join(root, *rel.split("/")) if rel else ""
          if not abs_path or not os.path.isfile(abs_path):
            continue
          # Prefer disk-walked entry if same path
          if any(e["relative_path"] == rel for e in entries):
            # Carry over license/source/notes from manual catalog
            for e in entries:
              if e["relative_path"] == rel:
                for key in ("license", "source", "notes", "label"):
                  if item.get(key):
                    e[key] = item[key]
                break
            continue
          existing_manual.append(item)
      except Exception:
        logger.exception("Could not merge prior catalog metadata")

    merged = entries + existing_manual
    return cls._write_catalog(merged)

  @classmethod
  def _write_catalog(cls, entries: list[dict[str, Any]]) -> dict[str, Any]:
    # Drop placeholder leftovers
    clean = [e for e in entries if not cls._looks_like_placeholder_entry(e)]
    catalog = {
      "version": CATALOG_VERSION,
      "product": "MediMentora",
      "module": "educational_healthy_xray_comparison",
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      "organization": ["body_part", "projection", "age_group", "gender"],
      "projections": list(XRAY_PROJECTIONS),
      "age_groups": list(XRAY_AGE_GROUPS),
      "genders": list(XRAY_REFERENCE_GENDERS),
      "body_parts": list(XRAY_BODY_PARTS),
      "gender_relevant_body_parts": list(XRAY_GENDER_RELEVANT_BODY_PARTS),
      "image_extensions": list(IMAGE_EXTENSIONS),
      "references": clean,
      "instructions": (
        "Add real healthy radiographs under "
        "body_part/projection/age_group/gender/, then call rebuild_catalog_from_disk() "
        "or restart with an empty catalog to auto-sync. Do not use drawings or icons."
      ),
    }
    with open(cls.catalog_path(), "w", encoding="utf-8") as f:
      json.dump(catalog, f, indent=2, ensure_ascii=False)
    logger.info(
      "Reference catalog written entries=%s root=%s",
      len(clean),
      cls.library_root(),
    )
    return catalog

  # Kept for backward-compatible test imports; never creates drawings.
  @classmethod
  def seed_placeholders(cls) -> dict[str, Any]:
    logger.warning(
      "seed_placeholders() is disabled — placeholders are not allowed. "
      "Rebuilding catalog from real image files only."
    )
    return cls.rebuild_catalog_from_disk()

  @classmethod
  def list_references(
    cls,
    *,
    body_part: str | None = None,
    projection: str | None = None,
    age_group: str | None = None,
    gender: str | None = None,
  ) -> list[ReferenceImage]:
    """Search healthy educational references (DB-backed)."""
    try:
      from app.services.xray.reference_xray_library_service import ReferenceXrayLibraryService

      rows, total = ReferenceXrayLibraryService.search(
        q=None,
        body_part=body_part,
        projection=projection,
        age_group=age_group,
        gender=gender,
        is_active=True,
        limit=500,
        offset=0,
      )
      # If the DB has rows (even if none match filters beyond this query), keep DB as source of truth.
      if total > 0:
        root = ReferenceXrayLibraryService.library_root()
        out: list[ReferenceImage] = []
        for row in rows:
          # Placeholder/synthetic safeguards (belt-and-suspenders; upload already rejects).
          blob = " ".join(
            str(x or "")
            for x in (
              row.anatomical_notes,
              row.title,
              row.source,
              row.license,
              row.public_id,
            )
          ).lower()
          if any(m in blob for m in PLACEHOLDER_MARKERS):
            continue

          rel = (row.image_path or "").replace("\\", "/")
          abs_path = ReferenceXrayLibraryService.resolve_path(rel) or ""
          out.append(
            ReferenceImage(
              id=(row.public_id or str(row.id or "")),
              body_part=row.body_part,
              projection=row.projection,
              age_group=row.age_group,
              gender=row.gender,
              relative_path=rel,
              absolute_path=abs_path,
              label=row.title or "Educational healthy reference",
              notes=row.anatomical_notes or row.description or "",
              license=row.license or "",
              source=row.source or "",
              gender_relevant=bool(getattr(row, "gender_is_relevant", lambda: False)()),
            )
          )
        return out
    except Exception:
      logger.exception("DB list_references failed; falling back to disk catalog")

    cls.ensure_library()
    refs = cls._load_references()
    out = []
    for ref in refs:
      if not os.path.isfile(ref.absolute_path):
        continue
      if body_part and ref.body_part.lower() != body_part.strip().lower():
        continue
      if projection and ref.projection.lower() != projection.strip().lower():
        continue
      if age_group and ref.age_group.lower() != age_group.strip().lower():
        continue
      if gender and ref.gender.lower() != gender.strip().lower():
        continue
      out.append(ref)
    return out

  @classmethod
  def select_reference(
    cls,
    *,
    body_part: str | None,
    patient_age: int | None = None,
    gender: str | None = None,
    projection: str | None = None,
    orientation: str | None = None,
    difficulty: str | None = None,
    limit_alternatives: int = 3,
  ) -> ReferenceSelectionResult:
    """Delegate to Module 6 weighted matching engine."""
    try:
      from app.services.xray.reference_matcher import ReferenceMatcher

      match = ReferenceMatcher.match(
        body_part=body_part,
        projection=projection,
        patient_age=patient_age,
        gender=gender,
        orientation=orientation,
        difficulty=difficulty,
        limit_alternatives=limit_alternatives,
      )
      # Convert MatchResult → legacy ReferenceSelectionResult for callers
      primary_img = None
      if match.primary:
        primary_img = cls._dict_to_reference_image(match.primary)
      alt_imgs = [cls._dict_to_reference_image(a) for a in match.alternatives if a]

      return ReferenceSelectionResult(
        success=match.success,
        primary=primary_img,
        alternatives=[a for a in alt_imgs if a],
        matched_body_part=match.matched_body_part,
        matched_age_group=match.matched_age_group,
        matched_projection=match.matched_projection,
        gender_used=match.gender_used,
        score=match.score,
        message=match.message,
        error_code=match.error_code,
      )
    except Exception:
      logger.exception("ReferenceMatcher.match failed — soft empty")
      return ReferenceSelectionResult(
        success=False,
        message=EMPTY_LIBRARY_MESSAGE,
        error_code="empty_library",
      )

  @classmethod
  def select_for_xray_row(cls, row) -> ReferenceSelectionResult:
    """Extract attributes from an XrayAnalysis row and delegate to the matcher."""
    try:
      from app.services.xray.reference_library.selector import ReferenceLibrarySelector

      body_part, projection, age, gender = ReferenceLibrarySelector._attrs_from_row(row)
      return cls.select_reference(
        body_part=body_part,
        patient_age=age,
        gender=gender,
        projection=projection,
      )
    except Exception:
      logger.exception("select_for_xray_row failed — soft empty")
      return ReferenceSelectionResult(
        success=False,
        message=EMPTY_LIBRARY_MESSAGE,
        error_code="empty_library",
      )

  @classmethod
  def form_options(cls) -> dict[str, Any]:
    try:
      from app.services.xray.reference_library_manager import ReferenceLibraryManager

      return ReferenceLibraryManager.form_options()
    except Exception:
      logger.exception("Manager form_options failed")
      return {
        "body_parts": list(XRAY_BODY_PARTS),
        "projections": list(XRAY_PROJECTIONS),
        "age_groups": list(XRAY_AGE_GROUPS),
        "genders": list(XRAY_REFERENCE_GENDERS),
        "total_references": 0,
        "library_ready": False,
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      }

  @classmethod
  def _load_references(cls) -> list[ReferenceImage]:
    path = cls.catalog_path()
    if not os.path.isfile(path):
      return []
    with open(path, encoding="utf-8") as f:
      data = json.load(f)
    root = cls.library_root()
    refs: list[ReferenceImage] = []
    for item in data.get("references") or []:
      if cls._looks_like_placeholder_entry(item):
        continue
      rel = str(item.get("relative_path") or "").replace("\\", "/")
      abs_path = os.path.join(root, *rel.split("/")) if rel else ""
      body = str(item.get("body_part") or "Other")
      refs.append(
        ReferenceImage(
          id=str(item.get("id") or rel),
          body_part=body,
          projection=str(item.get("projection") or "Other"),
          age_group=str(item.get("age_group") or "Adult"),
          gender=str(item.get("gender") or "Unisex"),
          relative_path=rel,
          absolute_path=abs_path,
          label=str(item.get("label") or "Educational healthy reference"),
          notes=str(item.get("notes") or ""),
          license=str(item.get("license") or ""),
          source=str(item.get("source") or ""),
          gender_relevant=bool(
            item.get("gender_relevant")
            if "gender_relevant" in item
            else body in XRAY_GENDER_RELEVANT_BODY_PARTS
          ),
        )
      )
    return refs

  @classmethod
  def age_group_from_age(cls, patient_age: int | None) -> str:
    if patient_age is None:
      return "Adult"
    try:
      age = int(patient_age)
    except (TypeError, ValueError):
      return "Adult"
    if age < 0:
      return "Adult"
    if age <= INFANT_AGE_MAX:
      return "Infant"
    if age <= CHILD_BAND_MAX:
      return "Child"
    if age <= TEEN_AGE_MAX:
      return "Teen"
    if age <= ADULT_AGE_MAX:
      return "Adult"
    return "Older Adult"

  @classmethod
  def normalize_age_group(cls, value: str | None) -> str | None:
    if not value:
      return None
    raw = value.strip().lower().replace("_", " ").replace("-", " ")
    mapping = {
      "infant": "Infant",
      "baby": "Infant",
      "neonate": "Infant",
      "newborn": "Infant",
      "child": "Child",
      "pediatric": "Child",
      "paediatric": "Child",
      "teen": "Teen",
      "teenager": "Teen",
      "adolescent": "Teen",
      "adult": "Adult",
      "older adult": "Older Adult",
      "olderadult": "Older Adult",
      "elderly": "Older Adult",
      "geriatric": "Older Adult",
    }
    return mapping.get(raw)

  @classmethod
  def normalize_body_part(cls, body_part: str | None) -> str:
    if not body_part:
      return "Other"
    raw = body_part.strip()
    for part in XRAY_BODY_PARTS:
      if part.lower() == raw.lower():
        return part
    aliases = {
      "thorax": "Chest",
      "cxr": "Chest",
      "lung": "Chest",
      "lungs": "Chest",
      "skull": "Skull",
      "cranium": "Skull",
      "head": "Skull",
      "abdomen": "Other",
      "c-spine": "Spine",
      "lumbar": "Spine",
      "cervical": "Spine",
      "collar bone": "Clavicle",
      "collarbone": "Clavicle",
      "thigh": "Femur",
    }
    return aliases.get(raw.lower(), "Other")

  @classmethod
  def normalize_gender(cls, gender: str | None) -> str | None:
    if not gender:
      return None
    g = gender.strip().lower()
    if g in ("m", "male", "man"):
      return "Male"
    if g in ("f", "female", "woman"):
      return "Female"
    if g in ("unisex", "any", "n/a", "na"):
      return "Unisex"
    if g in ("unknown", "unspecified", "prefer not to say", "other"):
      return "Unknown"
    return None

  @classmethod
  def normalize_orientation(cls, value: str | None) -> str | None:
    if not value:
      return None
    raw = value.strip().lower()
    mapping = {
      "left": "Left",
      "l": "Left",
      "lt": "Left",
      "right": "Right",
      "r": "Right",
      "rt": "Right",
      "bilateral": "Bilateral",
      "both": "Bilateral",
      "unknown": "Unknown",
      "n/a": "Unknown",
      "na": "Unknown",
    }
    return mapping.get(raw)

  @classmethod
  def normalize_projection(cls, value: str | None) -> str | None:
    if not value:
      return None
    raw = value.strip().lower().replace("_", " ").replace("-", " ")
    aliases = {
      "pa": "PA",
      "p a": "PA",
      "posteroanterior": "PA",
      "posterior anterior": "PA",
      "ap": "AP",
      "a p": "AP",
      "anteroposterior": "AP",
      "anterior posterior": "AP",
      "lateral": "Lateral",
      "lat": "Lateral",
      "side": "Lateral",
      "oblique": "Oblique",
      "obl": "Oblique",
      "axial": "Axial",
      "skyline": "Skyline",
      "merchant": "Skyline",
      "other": "Other",
      "unknown": "Other",
    }
    if raw in aliases:
      return aliases[raw]
    for proj in XRAY_PROJECTIONS:
      if proj.lower() == raw:
        return proj
    return None

  @classmethod
  def detect_projection(
    cls,
    *,
    explicit: str | None = None,
    clinical_extras: dict[str, Any] | None = None,
    reason_for_exam: str | None = None,
    symptoms: str | None = None,
    filename: str | None = None,
  ) -> str | None:
    """Detect projection/view from clinical fields and text cues."""
    extras = clinical_extras if isinstance(clinical_extras, dict) else {}
    for candidate in (
      explicit,
      extras.get("projection"),
      extras.get("view"),
      extras.get("view_position"),
    ):
      normalized = cls.normalize_projection(str(candidate) if candidate else None)
      if normalized:
        return normalized

    blob = " ".join(
      filter(
        None,
        [
          str(reason_for_exam or ""),
          str(symptoms or ""),
          str(filename or ""),
          str(extras.get("notes") or ""),
        ],
      )
    ).lower().replace("_", " ").replace("-", " ")
    patterns = (
      (r"\bpostero\s*anterior\b|\bpa\s+view\b|\bpa\b", "PA"),
      (r"\bantero\s*posterior\b|\bap\s+view\b|\bap\b", "AP"),
      (r"\blateral\b|\blat\.?\b", "Lateral"),
      (r"\boblique\b", "Oblique"),
    )
    for pattern, proj in patterns:
      if re.search(pattern, blob):
        return proj
    return None

  @classmethod
  def gender_is_relevant(cls, body_part: str | None) -> bool:
    part = cls.normalize_body_part(body_part)
    return part in XRAY_GENDER_RELEVANT_BODY_PARTS

  @classmethod
  def _dict_to_reference_image(cls, d: dict[str, Any]) -> ReferenceImage | None:
    """Convert a ``ReferenceXrayLibrary.to_dict()`` payload back to a runtime ``ReferenceImage``."""
    if not d:
      return None
    root = cls.library_root()
    rel = (d.get("image_path") or "").replace("\\", "/")
    abs_path = os.path.normpath(os.path.join(root, rel)) if rel else ""
    return ReferenceImage(
      id=d.get("public_id") or str(d.get("id", "")),
      label=d.get("title") or "",
      body_part=d.get("body_part") or "Other",
      projection=d.get("projection") or "Other",
      age_group=d.get("age_group") or "Adult",
      gender=d.get("gender") or "Unisex",
      absolute_path=abs_path,
      relative_path=rel,
      notes=d.get("anatomical_notes") or d.get("description") or "",
      source=d.get("source") or "",
      license=d.get("license") or "",
      gender_relevant=bool(d.get("gender_relevant")),
    )

  @classmethod
  def resolve_file(cls, relative_or_absolute: str) -> str | None:
    """Resolve a library path safely (prevent path traversal)."""
    if not relative_or_absolute:
      return None
    root = os.path.abspath(cls.library_root())
    candidate = relative_or_absolute
    if not os.path.isabs(candidate):
      candidate = os.path.join(root, candidate.replace("\\", "/").lstrip("/"))
    candidate = os.path.abspath(candidate)
    if not candidate.startswith(root + os.sep) and candidate != root:
      return None
    if not os.path.isfile(candidate):
      return None
    return candidate
