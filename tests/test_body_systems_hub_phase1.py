"""Phase 1 — Body Systems Learning Hub schema tests."""

from __future__ import annotations

from sqlalchemy import inspect

from app.extensions import db
from app.helpers.schema_patches import ensure_body_systems_hub_schema
from app.models.body_system_model import (
  BODY_SYSTEM_SEED,
  ORGAN_SEED,
  BodySystem,
  BodySystemCourse,
  BodySystemProgress,
  BodySystemQuiz,
  HubDisease,
  HubDiseaseClinicalCase,
  HubFlashcard,
  HubFlashcardFavorite,
  HubRecommendation,
  Organ,
  OrganLesson,
)


EXPECTED_TABLES = {
  "body_systems",
  "organs",
  "hub_diseases",
  "body_system_courses",
  "body_system_quizzes",
  "organ_lessons",
  "hub_disease_clinical_cases",
  "hub_flashcards",
  "hub_flashcard_favorites",
  "body_system_progress",
  "hub_recommendations",
}


def test_body_systems_hub_tables_exist(app_ctx):
  ensure_body_systems_hub_schema()
  names = set(inspect(db.engine).get_table_names())
  missing = EXPECTED_TABLES - names
  assert not missing, f"Missing hub tables: {sorted(missing)}"


def test_body_systems_seeded(app_ctx):
  ensure_body_systems_hub_schema()
  systems = BodySystem.query.filter_by(is_active=True).all()
  slugs = {s.slug for s in systems}
  expected = {item["slug"] for item in BODY_SYSTEM_SEED}
  assert expected.issubset(slugs)
  assert len(systems) >= len(BODY_SYSTEM_SEED)


def test_organs_seeded_under_systems(app_ctx):
  ensure_body_systems_hub_schema()
  organ_slugs = {o.slug for o in Organ.query.filter_by(is_active=True).all()}
  expected = {slug for slug, *_ in ORGAN_SEED}
  assert expected.issubset(organ_slugs)

  heart = Organ.query.filter_by(slug="heart").first()
  assert heart is not None
  assert heart.body_system is not None
  assert heart.body_system.slug == "circulatory"
  assert heart.region_key == "heart"


def test_hub_models_to_dict_safety(app_ctx):
  ensure_body_systems_hub_schema()
  system = BodySystem.query.filter_by(slug="respiratory").first()
  assert system is not None
  payload = system.to_dict()
  assert payload["safety"]["educational_only"] is True
  assert payload["safety"]["not_a_diagnosis"] is True
  assert "estimated_study_time" in payload


def test_ensure_body_systems_hub_schema_idempotent(app_ctx):
  ensure_body_systems_hub_schema()
  count_1 = BodySystem.query.count()
  organ_1 = Organ.query.count()
  ensure_body_systems_hub_schema()
  assert BodySystem.query.count() == count_1
  assert Organ.query.count() == organ_1


def test_junction_and_progress_models_importable():
  # Sanity: all Phase 1 models are importable / mapped
  assert BodySystemCourse.__tablename__ == "body_system_courses"
  assert BodySystemQuiz.__tablename__ == "body_system_quizzes"
  assert OrganLesson.__tablename__ == "organ_lessons"
  assert HubDiseaseClinicalCase.__tablename__ == "hub_disease_clinical_cases"
  assert HubFlashcard.__tablename__ == "hub_flashcards"
  assert HubFlashcardFavorite.__tablename__ == "hub_flashcard_favorites"
  assert BodySystemProgress.__tablename__ == "body_system_progress"
  assert HubRecommendation.__tablename__ == "hub_recommendations"
  assert HubDisease.__tablename__ == "hub_diseases"
