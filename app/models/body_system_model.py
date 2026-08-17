"""AI Human Body Systems Learning Hub — Phase 1 schema.

Extends MediMentora LMS without replacing Course / Lesson / Quiz / ClinicalCase.
Educational content only — not a diagnostic tool.
"""

from __future__ import annotations

from app.extensions import db
from app.utils import utc_now

# Canonical starter catalog (Phase 1 seed).
BODY_SYSTEM_SEED = (
  {
    "slug": "circulatory",
    "name": "Circulatory System",
    "short_description": "Heart, blood vessels, and blood circulation for oxygen and nutrient delivery.",
    "icon": "heart",
    "emoji": "🫀",
    "difficulty": "intermediate",
    "estimated_minutes": 180,
    "sort_order": 10,
  },
  {
    "slug": "respiratory",
    "name": "Respiratory System",
    "short_description": "Lungs and airways that exchange oxygen and carbon dioxide.",
    "icon": "lungs",
    "emoji": "🫁",
    "difficulty": "intermediate",
    "estimated_minutes": 150,
    "sort_order": 20,
  },
  {
    "slug": "nervous",
    "name": "Nervous System",
    "short_description": "Brain, spinal cord, and nerves that control sensation and movement.",
    "icon": "brain",
    "emoji": "🧠",
    "difficulty": "advanced",
    "estimated_minutes": 210,
    "sort_order": 30,
  },
  {
    "slug": "skeletal",
    "name": "Skeletal System",
    "short_description": "Bones, joints, and structural support for the human body.",
    "icon": "bone",
    "emoji": "🦴",
    "difficulty": "beginner",
    "estimated_minutes": 120,
    "sort_order": 40,
  },
  {
    "slug": "muscular",
    "name": "Muscular System",
    "short_description": "Skeletal, smooth, and cardiac muscle for movement and posture.",
    "icon": "muscle",
    "emoji": "💪",
    "difficulty": "beginner",
    "estimated_minutes": 120,
    "sort_order": 50,
  },
  {
    "slug": "digestive",
    "name": "Digestive System",
    "short_description": "Organs that break down food and absorb nutrients.",
    "icon": "digestive",
    "emoji": "🍽",
    "difficulty": "intermediate",
    "estimated_minutes": 150,
    "sort_order": 60,
  },
  {
    "slug": "immune",
    "name": "Immune System",
    "short_description": "Defense network that protects against infection and disease.",
    "icon": "shield",
    "emoji": "🛡",
    "difficulty": "advanced",
    "estimated_minutes": 160,
    "sort_order": 70,
  },
  {
    "slug": "endocrine",
    "name": "Endocrine System",
    "short_description": "Glands and hormones that regulate metabolism and growth.",
    "icon": "endocrine",
    "emoji": "🩺",
    "difficulty": "advanced",
    "estimated_minutes": 140,
    "sort_order": 80,
  },
  {
    "slug": "urinary",
    "name": "Urinary System",
    "short_description": "Kidneys and urinary tract that filter blood and balance fluids.",
    "icon": "kidney",
    "emoji": "🚽",
    "difficulty": "intermediate",
    "estimated_minutes": 130,
    "sort_order": 90,
  },
  {
    "slug": "reproductive",
    "name": "Reproductive System",
    "short_description": "Organs involved in reproduction and related physiology.",
    "icon": "reproductive",
    "emoji": "👶",
    "difficulty": "intermediate",
    "estimated_minutes": 140,
    "sort_order": 100,
  },
  {
    "slug": "integumentary",
    "name": "Integumentary System",
    "short_description": "Skin, hair, and nails — the body's protective outer layer.",
    "icon": "skin",
    "emoji": "🧴",
    "difficulty": "beginner",
    "estimated_minutes": 90,
    "sort_order": 110,
  },
)

# Starter organs for Phase 1 (expandable; Phase 4/5 will enrich content).
ORGAN_SEED = (
  ("heart", "Heart", "circulatory", "thorax", 10),
  ("lungs", "Lungs", "respiratory", "thorax", 10),
  ("brain", "Brain", "nervous", "head", 10),
  ("kidneys", "Kidneys", "urinary", "abdomen", 10),
  ("liver", "Liver", "digestive", "abdomen", 20),
  ("stomach", "Stomach", "digestive", "abdomen", 30),
  ("pancreas", "Pancreas", "digestive", "abdomen", 40),
  ("spleen", "Spleen", "immune", "abdomen", 10),
  ("bones", "Bones", "skeletal", "whole_body", 10),
  ("muscles", "Muscles", "muscular", "whole_body", 10),
)


class BodySystem(db.Model):
  """Canonical human body system for the Learning Hub."""

  __tablename__ = "body_systems"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
  name = db.Column(db.String(120), nullable=False, unique=True, index=True)
  short_description = db.Column(db.Text, nullable=True)
  long_description = db.Column(db.Text, nullable=True)
  icon = db.Column(db.String(80), nullable=True)
  emoji = db.Column(db.String(16), nullable=True)
  illustration_url = db.Column(db.String(500), nullable=True)
  difficulty = db.Column(db.String(20), default="intermediate")  # beginner|intermediate|advanced
  estimated_minutes = db.Column(db.Integer, default=120)
  lesson_count = db.Column(db.Integer, default=0)  # denormalized; refreshed by services
  sort_order = db.Column(db.Integer, default=0, index=True)
  is_active = db.Column(db.Boolean, default=True, index=True)
  is_published = db.Column(db.Boolean, default=True, index=True)
  category_id = db.Column(
    db.Integer, db.ForeignKey("course_categories.id", ondelete="SET NULL"), nullable=True, index=True
  )
  default_course_id = db.Column(
    db.Integer, db.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
  )
  meta_json = db.Column(db.JSON, nullable=True)  # future 3D / explorer metadata
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  category = db.relationship("CourseCategory", foreign_keys=[category_id])
  default_course = db.relationship("Course", foreign_keys=[default_course_id])
  organs = db.relationship(
    "Organ",
    back_populates="body_system",
    lazy="dynamic",
    cascade="all, delete-orphan",
    order_by="Organ.sort_order",
  )
  course_links = db.relationship(
    "BodySystemCourse",
    back_populates="body_system",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )
  quiz_links = db.relationship(
    "BodySystemQuiz",
    back_populates="body_system",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )
  diseases = db.relationship(
    "HubDisease",
    back_populates="body_system",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )
  progress_records = db.relationship(
    "BodySystemProgress",
    back_populates="body_system",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )

  def to_dict(self, *, include_counts: bool = True):
    data = {
      "id": self.id,
      "slug": self.slug,
      "name": self.name,
      "short_description": self.short_description,
      "long_description": self.long_description,
      "icon": self.icon,
      "emoji": self.emoji,
      "illustration_url": self.illustration_url,
      "difficulty": self.difficulty or "intermediate",
      "estimated_minutes": self.estimated_minutes or 0,
      "estimated_study_time": _format_study_time(self.estimated_minutes),
      "sort_order": self.sort_order or 0,
      "is_active": bool(self.is_active),
      "is_published": bool(self.is_published),
      "category_id": self.category_id,
      "default_course_id": self.default_course_id,
      "meta_json": self.meta_json or {},
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
      },
    }
    if include_counts:
      data["lesson_count"] = int(self.lesson_count or 0)
      data["organ_count"] = self.organs.filter_by(is_active=True).count()
      data["disease_count"] = self.diseases.filter_by(is_active=True).count()
    return data


class Organ(db.Model):
  """Organ within a body system (future-ready for 2D SVG / 3D explorer)."""

  __tablename__ = "organs"
  __table_args__ = (
    db.UniqueConstraint("body_system_id", "slug", name="uq_organs_system_slug"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  body_system_id = db.Column(
    db.Integer, db.ForeignKey("body_systems.id", ondelete="CASCADE"), nullable=False, index=True
  )
  slug = db.Column(db.String(80), nullable=False, index=True)
  name = db.Column(db.String(120), nullable=False, index=True)
  short_description = db.Column(db.Text, nullable=True)
  overview = db.Column(db.Text, nullable=True)
  location = db.Column(db.String(120), nullable=True)  # head|thorax|abdomen|whole_body|…
  region_key = db.Column(db.String(80), nullable=True)  # SVG / 3D hotspot id
  illustration_url = db.Column(db.String(500), nullable=True)
  animation_key = db.Column(db.String(80), nullable=True)  # e.g. heart_pumping
  content_json = db.Column(db.JSON, nullable=True)  # sections for Phase 4 organ pages
  learning_objectives = db.Column(db.JSON, nullable=True)
  sort_order = db.Column(db.Integer, default=0)
  is_active = db.Column(db.Boolean, default=True, index=True)
  is_published = db.Column(db.Boolean, default=True, index=True)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  body_system = db.relationship("BodySystem", back_populates="organs")
  lesson_links = db.relationship(
    "OrganLesson",
    back_populates="organ",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )
  diseases = db.relationship(
    "HubDisease",
    back_populates="organ",
    lazy="dynamic",
  )

  def to_dict(self):
    return {
      "id": self.id,
      "body_system_id": self.body_system_id,
      "slug": self.slug,
      "name": self.name,
      "short_description": self.short_description,
      "overview": self.overview,
      "location": self.location,
      "region_key": self.region_key or self.slug,
      "illustration_url": self.illustration_url,
      "animation_key": self.animation_key,
      "content_json": self.content_json or {},
      "learning_objectives": self.learning_objectives or [],
      "sort_order": self.sort_order or 0,
      "is_active": bool(self.is_active),
      "is_published": bool(self.is_published),
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }


class HubDisease(db.Model):
  """Educational disease entry for Disease Explorer (not a diagnosis)."""

  __tablename__ = "hub_diseases"
  __table_args__ = (
    db.UniqueConstraint("body_system_id", "slug", name="uq_hub_diseases_system_slug"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  body_system_id = db.Column(
    db.Integer, db.ForeignKey("body_systems.id", ondelete="CASCADE"), nullable=False, index=True
  )
  organ_id = db.Column(
    db.Integer, db.ForeignKey("organs.id", ondelete="SET NULL"), nullable=True, index=True
  )
  slug = db.Column(db.String(120), nullable=False, index=True)
  name = db.Column(db.String(200), nullable=False, index=True)
  short_description = db.Column(db.Text, nullable=True)
  content_json = db.Column(db.JSON, nullable=True)  # signs, symptoms, investigations, nursing, …
  difficulty = db.Column(db.String(20), default="intermediate")
  topic_tags = db.Column(db.JSON, nullable=True)
  is_active = db.Column(db.Boolean, default=True, index=True)
  is_published = db.Column(db.Boolean, default=True, index=True)
  sort_order = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  body_system = db.relationship("BodySystem", back_populates="diseases")
  organ = db.relationship("Organ", back_populates="diseases")
  case_links = db.relationship(
    "HubDiseaseClinicalCase",
    back_populates="disease",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )

  def to_dict(self):
    return {
      "id": self.id,
      "body_system_id": self.body_system_id,
      "organ_id": self.organ_id,
      "slug": self.slug,
      "name": self.name,
      "short_description": self.short_description,
      "content_json": self.content_json or {},
      "difficulty": self.difficulty or "intermediate",
      "topic_tags": self.topic_tags or [],
      "is_active": bool(self.is_active),
      "is_published": bool(self.is_published),
      "sort_order": self.sort_order or 0,
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "Disease content is for learning only and must not be used as a clinical diagnosis.",
      },
    }


class BodySystemCourse(db.Model):
  """Links LMS courses into a body system path."""

  __tablename__ = "body_system_courses"
  __table_args__ = (
    db.UniqueConstraint("body_system_id", "course_id", name="uq_body_system_course"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  body_system_id = db.Column(
    db.Integer, db.ForeignKey("body_systems.id", ondelete="CASCADE"), nullable=False, index=True
  )
  course_id = db.Column(
    db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
  )
  role = db.Column(db.String(40), default="related")  # primary|related|clinical
  sort_order = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)

  body_system = db.relationship("BodySystem", back_populates="course_links")
  course = db.relationship("Course")

  def to_dict(self):
    return {
      "id": self.id,
      "body_system_id": self.body_system_id,
      "course_id": self.course_id,
      "role": self.role or "related",
      "sort_order": self.sort_order or 0,
    }


class BodySystemQuiz(db.Model):
  """Links existing quizzes to a body system."""

  __tablename__ = "body_system_quizzes"
  __table_args__ = (
    db.UniqueConstraint("body_system_id", "quiz_id", name="uq_body_system_quiz"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  body_system_id = db.Column(
    db.Integer, db.ForeignKey("body_systems.id", ondelete="CASCADE"), nullable=False, index=True
  )
  quiz_id = db.Column(
    db.Integer, db.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
  )
  is_required = db.Column(db.Boolean, default=False)
  sort_order = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)

  body_system = db.relationship("BodySystem", back_populates="quiz_links")
  quiz = db.relationship("Quiz")

  def to_dict(self):
    return {
      "id": self.id,
      "body_system_id": self.body_system_id,
      "quiz_id": self.quiz_id,
      "is_required": bool(self.is_required),
      "sort_order": self.sort_order or 0,
    }


class OrganLesson(db.Model):
  """Links LMS lessons to an organ (hotspot / deep-link)."""

  __tablename__ = "organ_lessons"
  __table_args__ = (
    db.UniqueConstraint("organ_id", "lesson_id", name="uq_organ_lesson"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  organ_id = db.Column(
    db.Integer, db.ForeignKey("organs.id", ondelete="CASCADE"), nullable=False, index=True
  )
  lesson_id = db.Column(
    db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
  )
  hotspot_id = db.Column(db.String(80), nullable=True)
  sort_order = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)

  organ = db.relationship("Organ", back_populates="lesson_links")
  lesson = db.relationship("Lesson")

  def to_dict(self):
    return {
      "id": self.id,
      "organ_id": self.organ_id,
      "lesson_id": self.lesson_id,
      "hotspot_id": self.hotspot_id,
      "sort_order": self.sort_order or 0,
    }


class HubDiseaseClinicalCase(db.Model):
  """Links educational hub diseases to existing clinical cases."""

  __tablename__ = "hub_disease_clinical_cases"
  __table_args__ = (
    db.UniqueConstraint("disease_id", "clinical_case_id", name="uq_hub_disease_case"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  disease_id = db.Column(
    db.Integer, db.ForeignKey("hub_diseases.id", ondelete="CASCADE"), nullable=False, index=True
  )
  clinical_case_id = db.Column(
    db.Integer, db.ForeignKey("clinical_cases.id", ondelete="CASCADE"), nullable=False, index=True
  )
  sort_order = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)

  disease = db.relationship("HubDisease", back_populates="case_links")
  clinical_case = db.relationship("ClinicalCase")

  def to_dict(self):
    return {
      "id": self.id,
      "disease_id": self.disease_id,
      "clinical_case_id": self.clinical_case_id,
      "sort_order": self.sort_order or 0,
    }


class HubFlashcard(db.Model):
  """Flashcards for body-system / organ / disease revision (Phase 8-ready)."""

  __tablename__ = "hub_flashcards"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  body_system_id = db.Column(
    db.Integer, db.ForeignKey("body_systems.id", ondelete="CASCADE"), nullable=True, index=True
  )
  organ_id = db.Column(
    db.Integer, db.ForeignKey("organs.id", ondelete="SET NULL"), nullable=True, index=True
  )
  disease_id = db.Column(
    db.Integer, db.ForeignKey("hub_diseases.id", ondelete="SET NULL"), nullable=True, index=True
  )
  lesson_id = db.Column(
    db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True
  )
  owner_user_id = db.Column(
    db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
  )
  book_id = db.Column(
    db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True
  )
  course_id = db.Column(
    db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True
  )
  module_id = db.Column(
    db.Integer, db.ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True
  )
  topic_id = db.Column(
    db.Integer, db.ForeignKey("course_topics.id", ondelete="SET NULL"), nullable=True, index=True
  )
  front_text = db.Column(db.Text, nullable=False)
  back_text = db.Column(db.Text, nullable=False)
  card_level = db.Column(db.String(40), default="basic")  # basic|advanced|exam_revision
  source_json = db.Column(db.JSON, nullable=True)
  source_hash = db.Column(db.String(64), nullable=True, index=True)
  generation_hash = db.Column(db.String(64), nullable=True, index=True)
  origin = db.Column(db.String(40), nullable=True, index=True)
  generation_method = db.Column(db.String(40), nullable=True)
  generated_at = db.Column(db.DateTime, nullable=True)
  topic_tags = db.Column(db.JSON, nullable=True)
  is_published = db.Column(db.Boolean, default=True, index=True)
  created_by = db.Column(
    db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
  )
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  def to_dict(self):
    return {
      "id": self.id,
      "body_system_id": self.body_system_id,
      "organ_id": self.organ_id,
      "disease_id": self.disease_id,
      "lesson_id": self.lesson_id,
      "book_id": self.book_id,
      "course_id": self.course_id,
      "module_id": self.module_id,
      "topic_id": self.topic_id,
      "front_text": self.front_text,
      "back_text": self.back_text,
      "card_level": self.card_level or "basic",
      "topic_tags": self.topic_tags or [],
      "source": self.source_json,
      "origin": self.origin,
      "generation_method": self.generation_method,
      "generated_at": self.generated_at.isoformat() if self.generated_at else None,
      "is_published": bool(self.is_published),
      "created_by": self.created_by,
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }


class HubFlashcardFavorite(db.Model):
  """User favorites for hub flashcards (spaced-repetition ready)."""

  __tablename__ = "hub_flashcard_favorites"
  __table_args__ = (
    db.UniqueConstraint("user_id", "flashcard_id", name="uq_hub_flashcard_favorite"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(
    db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
  )
  flashcard_id = db.Column(
    db.Integer, db.ForeignKey("hub_flashcards.id", ondelete="CASCADE"), nullable=False, index=True
  )
  # Phase 8 — spaced-repetition ready fields (unused by scheduler yet)
  ease_factor = db.Column(db.Float, default=2.5)
  interval_days = db.Column(db.Integer, default=0)
  repetitions = db.Column(db.Integer, default=0)
  status = db.Column(db.String(30), default="learning", index=True)
  correct_count = db.Column(db.Integer, default=0)
  incorrect_count = db.Column(db.Integer, default=0)
  review_count = db.Column(db.Integer, default=0)
  last_rating = db.Column(db.String(30), nullable=True)
  next_review_at = db.Column(db.DateTime, nullable=True, index=True)
  last_reviewed_at = db.Column(db.DateTime, nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now)

  flashcard = db.relationship("HubFlashcard")

  def to_dict(self, *, include_card: bool = False):
    data = {
      "id": self.id,
      "user_id": self.user_id,
      "flashcard_id": self.flashcard_id,
      "ease_factor": float(self.ease_factor) if self.ease_factor is not None else 2.5,
      "interval_days": int(self.interval_days or 0),
      "repetitions": int(self.repetitions or 0),
      "status": self.status or "learning",
      "correct_count": int(self.correct_count or 0),
      "incorrect_count": int(self.incorrect_count or 0),
      "review_count": int(self.review_count or 0),
      "last_rating": self.last_rating,
      "next_review_at": self.next_review_at.isoformat() if self.next_review_at else None,
      "last_reviewed_at": self.last_reviewed_at.isoformat() if self.last_reviewed_at else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "spaced_repetition": {
        "available": True,
        "future_ready": True,
        "note": "Review scheduling uses stored ease, repetition, interval, and due-date fields.",
      },
    }
    if include_card and self.flashcard:
      data["flashcard"] = self.flashcard.to_dict()
    return data



class BodySystemProgress(db.Model):
  """Per-user hub progress overlay (does not replace course_progress)."""

  __tablename__ = "body_system_progress"
  __table_args__ = (
    db.UniqueConstraint("user_id", "body_system_id", name="uq_body_system_progress_user"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(
    db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
  )
  body_system_id = db.Column(
    db.Integer, db.ForeignKey("body_systems.id", ondelete="CASCADE"), nullable=False, index=True
  )
  status = db.Column(db.String(30), default="not_started", index=True)
  # not_started | in_progress | completed
  progress_percent = db.Column(db.Float, default=0)
  study_minutes = db.Column(db.Integer, default=0)
  lessons_completed = db.Column(db.Integer, default=0)
  lessons_total = db.Column(db.Integer, default=0)
  last_course_id = db.Column(
    db.Integer, db.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
  )
  last_lesson_id = db.Column(
    db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True
  )
  last_organ_id = db.Column(
    db.Integer, db.ForeignKey("organs.id", ondelete="SET NULL"), nullable=True
  )
  started_at = db.Column(db.DateTime, nullable=True)
  completed_at = db.Column(db.DateTime, nullable=True)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  body_system = db.relationship("BodySystem", back_populates="progress_records")
  user = db.relationship("User")

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "body_system_id": self.body_system_id,
      "status": self.status or "not_started",
      "progress_percent": float(self.progress_percent or 0),
      "study_minutes": int(self.study_minutes or 0),
      "lessons_completed": int(self.lessons_completed or 0),
      "lessons_total": int(self.lessons_total or 0),
      "last_course_id": self.last_course_id,
      "last_lesson_id": self.last_lesson_id,
      "last_organ_id": self.last_organ_id,
      "started_at": self.started_at.isoformat() if self.started_at else None,
      "completed_at": self.completed_at.isoformat() if self.completed_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }


class HubRecommendation(db.Model):
  """Personalized hub recommendations (reports / x-ray / weak topics)."""

  __tablename__ = "hub_recommendations"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(
    db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
  )
  body_system_id = db.Column(
    db.Integer, db.ForeignKey("body_systems.id", ondelete="SET NULL"), nullable=True, index=True
  )
  organ_id = db.Column(
    db.Integer, db.ForeignKey("organs.id", ondelete="SET NULL"), nullable=True, index=True
  )
  disease_id = db.Column(
    db.Integer, db.ForeignKey("hub_diseases.id", ondelete="SET NULL"), nullable=True, index=True
  )
  course_id = db.Column(
    db.Integer, db.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
  )
  lesson_id = db.Column(
    db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True
  )
  source_type = db.Column(db.String(40), nullable=False, index=True)
  # xray | report | quiz_weak | search | manual | progress
  source_id = db.Column(db.Integer, nullable=True, index=True)
  title = db.Column(db.String(255), nullable=False)
  reason = db.Column(db.Text, nullable=True)
  href = db.Column(db.String(500), nullable=True)
  priority = db.Column(db.Integer, default=50, index=True)
  is_read = db.Column(db.Boolean, default=False, index=True)
  meta_json = db.Column(db.JSON, nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now, index=True)

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "body_system_id": self.body_system_id,
      "organ_id": self.organ_id,
      "disease_id": self.disease_id,
      "course_id": self.course_id,
      "lesson_id": self.lesson_id,
      "source_type": self.source_type,
      "source_id": self.source_id,
      "title": self.title,
      "reason": self.reason,
      "href": self.href,
      "priority": self.priority or 50,
      "is_read": bool(self.is_read),
      "meta_json": self.meta_json or {},
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }


class HubCertificate(db.Model):
  """Educational completion certificate for a body system (Phase 13).

  Not a professional license or clinical credential.
  """

  __tablename__ = "hub_certificates"
  __table_args__ = (
    db.UniqueConstraint("user_id", "body_system_id", name="uq_hub_cert_user_system"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(
    db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
  )
  body_system_id = db.Column(
    db.Integer, db.ForeignKey("body_systems.id", ondelete="CASCADE"), nullable=False, index=True
  )
  certificate_number = db.Column(db.String(100), nullable=False, unique=True)
  title = db.Column(db.String(255), nullable=False)
  file_path = db.Column(db.String(500), nullable=True)
  progress_percent = db.Column(db.Float, default=100.0)
  study_minutes = db.Column(db.Integer, default=0)
  issued_at = db.Column(db.DateTime, default=utc_now, index=True)
  meta_json = db.Column(db.JSON, nullable=True)

  body_system = db.relationship("BodySystem")

  def to_dict(self):
    system = self.body_system
    return {
      "id": self.id,
      "user_id": self.user_id,
      "body_system_id": self.body_system_id,
      "certificate_number": self.certificate_number,
      "title": self.title,
      "file_path": self.file_path,
      "progress_percent": float(self.progress_percent or 100),
      "study_minutes": int(self.study_minutes or 0),
      "issued_at": self.issued_at.isoformat() if self.issued_at else None,
      "body_system": system.to_dict(include_counts=False) if system else None,
      "href": f"/learning/body-systems/{system.slug}" if system else "/learning/body-systems",
      "download_url": f"/api/learning/hub/certificates/{self.id}/download",
      "meta_json": self.meta_json or {},
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "not_a_license": True,
        "note": (
          "This certificate confirms educational study progress in MediMentora. "
          "It is not a professional license, clinical credential, or diagnosis."
        ),
      },
    }


def _format_study_time(minutes: int | None) -> str:
  mins = int(minutes or 0)
  if mins <= 0:
    return "—"
  if mins < 60:
    return f"{mins} min"
  hours = mins / 60
  if hours == int(hours):
    return f"{int(hours)} hr"
  return f"{hours:.1f} hr"
