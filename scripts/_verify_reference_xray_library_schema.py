"""Verify Module 1 — reference_xray_library database schema."""

from __future__ import annotations

from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.helpers.schema_patches import ensure_xray_reference_library_schema
from app.models.reference_xray_library_model import (
  REFERENCE_AGE_GROUPS,
  REFERENCE_BODY_PARTS,
  REFERENCE_DIFFICULTIES,
  REFERENCE_GENDERS,
  REFERENCE_ORIENTATIONS,
  REFERENCE_PROJECTIONS,
  ReferenceXrayLibrary,
  reference_library_taxonomy,
)
from app.models.user_model import User
from app.utils import utc_now

REQUIRED_COLUMNS = {
  "id",
  "title",
  "body_part",
  "projection",
  "orientation",
  "age_group",
  "gender",
  "image_path",
  "thumbnail_path",
  "source",
  "license",
  "description",
  "anatomical_notes",
  "difficulty",
  "is_active",
  "uploaded_by",
  "created_at",
  "updated_at",
}


def main() -> int:
  app = create_app()
  with app.app_context():
    ensure_xray_reference_library_schema()
    ensure_xray_reference_library_schema()  # idempotent

    tables = set(inspect(db.engine).get_table_names())
    assert "reference_xray_library" in tables, "reference_xray_library table missing"

    cols = {c["name"] for c in inspect(db.engine).get_columns("reference_xray_library")}
    missing = sorted(REQUIRED_COLUMNS - cols)
    print("=== reference_xray_library columns ===")
    for name in sorted(REQUIRED_COLUMNS):
      print(f"  [{'OK' if name in cols else 'MISSING'}] {name}")
    if missing:
      print("MISSING:", missing)
      return 1

    tax = reference_library_taxonomy()
    assert "Finger" in REFERENCE_BODY_PARTS and "Skull" in REFERENCE_BODY_PARTS
    assert "Axial" in REFERENCE_PROJECTIONS and "Skyline" in REFERENCE_PROJECTIONS
    assert "Infant" in REFERENCE_AGE_GROUPS and "Older Adult" in REFERENCE_AGE_GROUPS
    assert "Unknown" in REFERENCE_GENDERS
    assert "Bilateral" in REFERENCE_ORIENTATIONS
    assert "Beginner" in REFERENCE_DIFFICULTIES
    assert tax["table"] == "reference_xray_library"
    print()
    print("Taxonomy OK:", {k: len(v) if isinstance(v, list) else v for k, v in tax.items()})

    user = User.query.first()
    if not user:
      print("No user found — skipping insert smoke test.")
    else:
      now = utc_now()
      row = ReferenceXrayLibrary(
        title="Healthy Chest PA Adult (smoke)",
        body_part="Chest",
        projection="PA",
        orientation="Unknown",
        age_group="Adult",
        gender="Unisex",
        image_path="chest/pa/adult/unisex/smoke_module1.png",
        thumbnail_path="thumbnails/smoke_module1.png",
        source="Educational smoke test",
        license="Internal test only",
        description="Schema verification row — not a real radiograph.",
        anatomical_notes="Lung fields, heart border, diaphragm.",
        difficulty="Beginner",
        is_active=True,
        uploaded_by=user.id,
        public_id="smoke_module1_ref",
        created_at=now,
        updated_at=now,
      )
      db.session.add(row)
      db.session.commit()
      rid = row.id
      payload = row.to_dict()
      assert payload["body_part"] == "Chest"
      assert payload["projection"] == "PA"
      assert payload["orientation"] == "Unknown"
      assert payload["safety"]["no_placeholder_images"] is True
      db.session.delete(row)
      db.session.commit()
      print(f"Smoke insert/delete OK (id={rid})")

    print()
    print("Module 1 — Database Schema verified.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
