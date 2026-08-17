"""Lightweight schema patches for environments without Alembic migrations."""

from __future__ import annotations

import logging
import os

from sqlalchemy import inspect, text

from app.extensions import db

logger = logging.getLogger(__name__)


# Columns required for the professional History module.
REPORT_HISTORY_COLUMNS = (
    ("batch_id", "VARCHAR(64) NULL", True),
    ("original_filename", "VARCHAR(255) NULL", False),
    ("stored_filename", "VARCHAR(255) NULL", False),
    ("file_size", "INT NULL", False),
    ("report_type", "VARCHAR(50) NULL", True),
    ("page_count", "INT NULL", False),
    ("ocr_confidence", "FLOAT NULL", False),
    ("analysis_confidence", "VARCHAR(20) NULL", False),
    ("structured_json", "JSON NULL", False),
    ("analysis_date", "DATETIME NULL", False),
    ("updated_at", "DATETIME NULL", False),
)


def ensure_report_batch_columns() -> None:
    """Backward-compatible entry point used by run.py / app factory."""
    ensure_report_history_schema()


def ensure_report_history_schema() -> None:
    """Add history-related columns/indexes to reports if missing. Never drops data."""
    try:
        inspector = inspect(db.engine)
        if "reports" not in inspector.get_table_names():
            return

        existing = {col["name"] for col in inspector.get_columns("reports")}
        statements: list[str] = []

        for name, ddl, needs_index in REPORT_HISTORY_COLUMNS:
            if name not in existing:
                statements.append(f"ALTER TABLE reports ADD COLUMN {name} {ddl}")
                if needs_index:
                    statements.append(f"CREATE INDEX ix_reports_{name} ON reports ({name})")

        # Status index for filters
        indexes = {ix["name"] for ix in inspector.get_indexes("reports")}
        if "status" in existing and "ix_reports_status" not in indexes:
            statements.append("CREATE INDEX ix_reports_status ON reports (status)")
        if "report_type" in existing | {n for n, _, _ in REPORT_HISTORY_COLUMNS} and "ix_reports_report_type" not in indexes:
            # Will be created after column add if needed — check again below
            pass

        if not statements:
            _backfill_stored_filenames()
            return

        with db.engine.begin() as conn:
            for stmt in statements:
                try:
                    conn.execute(text(stmt))
                    logger.info("Applied schema patch: %s", stmt)
                except Exception as exc:
                    logger.warning("Schema patch skipped (%s): %s", stmt, exc)

        # Ensure report_type index after column exists
        inspector = inspect(db.engine)
        existing = {col["name"] for col in inspector.get_columns("reports")}
        indexes = {ix["name"] for ix in inspector.get_indexes("reports")}
        if "report_type" in existing and "ix_reports_report_type" not in indexes:
            try:
                with db.engine.begin() as conn:
                    conn.execute(text("CREATE INDEX ix_reports_report_type ON reports (report_type)"))
            except Exception as exc:
                logger.warning("report_type index skipped: %s", exc)

        _backfill_stored_filenames()
        logger.info("Report history schema verified.")
    except Exception:
        logger.exception("Failed to ensure report history schema")


def _backfill_stored_filenames() -> None:
    """Populate stored_filename from file_path for older rows."""
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, file_path FROM reports "
                    "WHERE (stored_filename IS NULL OR stored_filename = '') "
                    "AND file_path IS NOT NULL"
                )
            ).fetchall()
            for row in rows:
                report_id, file_path = row[0], row[1]
                if not file_path:
                    continue
                stored = os.path.basename(file_path)
                conn.execute(
                    text("UPDATE reports SET stored_filename = :stored WHERE id = :id"),
                    {"stored": stored, "id": report_id},
                )
            if rows:
                logger.info("Backfilled stored_filename for %d report(s)", len(rows))
    except Exception:
        logger.exception("stored_filename backfill failed")


def ensure_xray_analysis_schema() -> None:
    """Create xray_analysis table if missing (safe for existing databases)."""
    try:
        inspector = inspect(db.engine)
        if "xray_analysis" in inspector.get_table_names():
            _ensure_xray_optional_columns(inspector)
            return

        # Create only the XrayAnalysis table without touching others
        from app.models.xray_analysis_model import XrayAnalysis  # noqa: F401

        XrayAnalysis.__table__.create(bind=db.engine, checkfirst=True)
        logger.info("Created xray_analysis table.")
    except Exception:
        logger.exception("Failed to ensure xray_analysis schema")


def _ensure_xray_optional_columns(inspector) -> None:
    """Add future-safe columns to xray_analysis if the table already exists."""
    existing = {col["name"] for col in inspector.get_columns("xray_analysis")}
    optional = (
        ("batch_id", "VARCHAR(64) NULL"),
        ("stored_filename", "VARCHAR(255) NULL"),
        ("file_type", "VARCHAR(20) NULL"),
        ("file_size", "INT NULL"),
        ("content_hash", "VARCHAR(64) NULL"),
        ("body_part", "VARCHAR(50) NULL"),
        # Patient Clinical Information
        ("patient_age", "INT NULL"),
        ("gender", "VARCHAR(40) NULL"),
        ("symptoms", "TEXT NULL"),
        ("reason_for_exam", "TEXT NULL"),
        ("smoking_history", "VARCHAR(40) NULL"),
        ("clinical_extras", "JSON NULL"),
        ("preprocessed_path", "VARCHAR(500) NULL"),
        ("heatmap_path", "VARCHAR(500) NULL"),
        ("heatmap_meta", "JSON NULL"),
        ("image_quality", "JSON NULL"),
        ("preprocess_meta", "JSON NULL"),
        ("body_detection", "JSON NULL"),
        ("projection_detection", "JSON NULL"),
        ("model_routing", "JSON NULL"),
        ("ensemble_result", "JSON NULL"),
        ("structured_findings", "JSON NULL"),
        # Educational Healthy X-Ray Comparison
        ("reference_image_path", "VARCHAR(500) NULL"),
        ("comparison_summary", "TEXT NULL"),
        ("comparison_generated_at", "DATETIME NULL"),
        ("structured_explanation", "JSON NULL"),
        ("learning_recommendations", "JSON NULL"),
        ("disclaimer", "TEXT NULL"),
        ("model_name", "VARCHAR(100) NULL"),
        ("analysis_version", "VARCHAR(40) NULL"),
        ("error_message", "TEXT NULL"),
    )
    statements = []
    for name, ddl in optional:
        if name not in existing:
            statements.append(f"ALTER TABLE xray_analysis ADD COLUMN {name} {ddl}")

    # Helpful indexes for history filters
    indexes = {ix["name"] for ix in inspector.get_indexes("xray_analysis")}
    all_cols = existing | {n for n, _ in optional}
    index_specs = (
        ("body_part", "ix_xray_analysis_body_part"),
        ("content_hash", "ix_xray_analysis_content_hash"),
        ("patient_age", "ix_xray_analysis_patient_age"),
        ("gender", "ix_xray_analysis_gender"),
        ("smoking_history", "ix_xray_analysis_smoking_history"),
        ("upload_date", "ix_xray_analysis_upload_date"),
    )
    for col, ix_name in index_specs:
        if col in all_cols and ix_name not in indexes:
            statements.append(f"CREATE INDEX {ix_name} ON xray_analysis ({col})")

    if not statements:
        return

    with db.engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                logger.info("Applied xray schema patch: %s", stmt)
            except Exception as exc:
                logger.warning("Xray schema patch skipped (%s): %s", stmt, exc)


def ensure_learning_schema() -> None:
    """Create LMS tables and patch existing course/lesson/quiz columns safely."""
    try:
        from app.models.course_model import (  # noqa: F401
            CourseBookmark,
            CourseCategory,
            CourseModule,
            CourseTopic,
            CourseProgress,
            CourseReview,
            LessonResource,
            LessonVideo,
        )
        from app.models.quiz_model import QuizAnswer  # noqa: F401

        # Create new tables first (checkfirst=True)
        for table in (
            CourseCategory.__table__,
            CourseModule.__table__,
            CourseTopic.__table__,
            LessonResource.__table__,
            LessonVideo.__table__,
            CourseProgress.__table__,
            CourseBookmark.__table__,
            CourseReview.__table__,
            QuizAnswer.__table__,
        ):
            table.create(bind=db.engine, checkfirst=True)

        inspector = inspect(db.engine)
        _add_columns_if_missing(
            inspector,
            "courses",
            (
                ("category_id", "INT NULL"),
                ("instructor_name", "VARCHAR(150) NULL"),
                ("instructor_id", "INT NULL"),
                ("thumbnail_url", "VARCHAR(500) NULL"),
                ("banner_url", "VARCHAR(500) NULL"),
                ("learning_objectives", "JSON NULL"),
                ("prerequisites", "JSON NULL"),
                ("rating_avg", "FLOAT NULL"),
                ("rating_count", "INT NULL"),
                ("enrollment_count", "INT NULL"),
                ("certificate_eligible", "BOOLEAN NULL"),
                ("owner_user_id", "INT NULL"),
                ("source_book_id", "INT NULL"),
                ("origin", "VARCHAR(40) NOT NULL DEFAULT 'manual'"),
                ("generation_status", "VARCHAR(30) NULL"),
                ("lesson_generation_status", "VARCHAR(30) NULL"),
                ("question_generation_status", "VARCHAR(30) NULL"),
                ("quiz_generation_status", "VARCHAR(30) NULL"),
                ("flashcard_generation_status", "VARCHAR(30) NULL"),
                ("source_structure_version", "VARCHAR(20) NULL"),
                ("source_json", "JSON NULL"),
            ),
        )
        inspector = inspect(db.engine)
        _add_columns_if_missing(
            inspector,
            "course_modules",
            (
                ("parent_module_id", "INT NULL"),
                ("structure_type", "VARCHAR(30) NOT NULL DEFAULT 'module'"),
                ("source_node_id", "VARCHAR(80) NULL"),
                ("page_start", "INT NULL"),
                ("page_end", "INT NULL"),
                ("source_json", "JSON NULL"),
            ),
        )
        inspector = inspect(db.engine)
        _add_indexes_if_missing(
            inspector,
            "courses",
            (
                (("owner_user_id",), "ix_courses_owner_user_id", False),
                (("source_book_id",), "uq_courses_source_book_id", True),
                (("origin",), "ix_courses_origin", False),
                (("generation_status",), "ix_courses_generation_status", False),
                (("question_generation_status",), "ix_courses_question_generation_status", False),
                (("quiz_generation_status",), "ix_courses_quiz_generation_status", False),
                (("flashcard_generation_status",), "ix_courses_flashcard_generation_status", False),
            ),
        )
        _add_indexes_if_missing(
            inspector,
            "course_modules",
            (
                (("parent_module_id",), "ix_course_modules_parent_module_id", False),
                (("course_id", "source_node_id"), "uq_course_module_source_node", True),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "lessons",
            (
                ("module_id", "INT NULL"),
                ("topic_id", "INT NULL"),
                ("summary", "TEXT NULL"),
                ("is_published", "BOOLEAN NULL"),
                ("updated_at", "DATETIME NULL"),
                ("content_json", "JSON NULL"),
                ("source_json", "JSON NULL"),
                ("source_hash", "VARCHAR(64) NULL"),
                ("origin", "VARCHAR(40) NOT NULL DEFAULT 'manual'"),
                ("generation_method", "VARCHAR(40) NULL"),
                ("difficulty_level", "VARCHAR(20) NULL"),
                ("generated_at", "DATETIME NULL"),
            ),
        )
        inspector = inspect(db.engine)
        _add_indexes_if_missing(
            inspector,
            "lessons",
            (
                (("topic_id",), "uq_lessons_topic_id", True),
                (("source_hash",), "ix_lessons_source_hash", False),
                (("origin",), "ix_lessons_origin", False),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "quizzes",
            (
                ("quiz_type", "VARCHAR(40) NULL"),
                ("course_id", "INT NULL"),
                ("lesson_id", "INT NULL"),
                ("passing_score", "FLOAT NULL"),
                ("source_book_id", "INT NULL"),
                ("source_question_bank_id", "INT NULL"),
                ("owner_user_id", "INT NULL"),
                ("scope_type", "VARCHAR(30) NULL"),
                ("scope_id", "INT NULL"),
                ("question_mode", "VARCHAR(30) NULL"),
                ("requested_question_count", "INT NULL"),
                ("generation_hash", "VARCHAR(64) NULL"),
                ("generated_at", "DATETIME NULL"),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "questions",
            (
                ("question_type", "VARCHAR(40) NULL"),
                ("image_url", "VARCHAR(500) NULL"),
                ("order_index", "INT NULL"),
                ("user_id", "INT NULL"),
                ("book_id", "INT NULL"),
                ("course_id", "INT NULL"),
                ("module_id", "INT NULL"),
                ("topic_id", "INT NULL"),
                ("lesson_id", "INT NULL"),
                ("difficulty", "VARCHAR(20) NULL"),
                ("priority_level", "VARCHAR(20) NULL"),
                ("priority_score", "INT NULL"),
                ("priority_reason", "VARCHAR(500) NULL"),
                ("learning_objective", "VARCHAR(500) NULL"),
                ("source_json", "JSON NULL"),
                ("source_hash", "VARCHAR(64) NULL"),
                ("origin", "VARCHAR(40) NULL"),
                ("generation_method", "VARCHAR(40) NULL"),
                ("generated_at", "DATETIME NULL"),
            ),
        )
        inspector = inspect(db.engine)
        _add_indexes_if_missing(
            inspector,
            "quizzes",
            (
                (("source_book_id",), "ix_quizzes_source_book_id", False),
                (("source_question_bank_id",), "ix_quizzes_source_question_bank_id", False),
                (("owner_user_id",), "ix_quizzes_owner_user_id", False),
                (("scope_type", "scope_id"), "ix_quizzes_scope", False),
                (("generation_hash",), "ix_quizzes_generation_hash", False),
            ),
        )
        _add_indexes_if_missing(
            inspector,
            "questions",
            (
                (("book_id", "lesson_id"), "ix_questions_book_lesson", False),
                (("topic_id", "difficulty"), "ix_questions_topic_difficulty", False),
                (("priority_level",), "ix_questions_priority_level", False),
                (("source_hash",), "ix_questions_source_hash", False),
                (("origin",), "ix_questions_origin", False),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "results",
            (
                ("passed", "BOOLEAN NULL"),
                ("attempt_number", "INT NULL"),
                ("book_id", "INT NULL"),
                ("course_id", "INT NULL"),
                ("time_taken_seconds", "INT NULL"),
                ("topic_breakdown_json", "JSON NULL"),
                ("review_json", "JSON NULL"),
                ("quiz_mode", "VARCHAR(30) NULL"),
            ),
        )
        inspector = inspect(db.engine)
        _add_indexes_if_missing(
            inspector,
            "results",
            (
                (("book_id", "user_id"), "ix_results_book_user", False),
                (("course_id", "user_id"), "ix_results_course_user", False),
            ),
        )

        _seed_course_categories_if_empty()
        _link_existing_courses_to_categories()
        _backfill_learning_booleans()
        logger.info("Learning LMS schema verified.")
    except Exception:
        logger.exception("Failed to ensure learning schema")


def _add_columns_if_missing(inspector, table_name: str, columns: tuple[tuple[str, str], ...]) -> None:
    if table_name not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    statements = [
        f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}"
        for name, ddl in columns
        if name not in existing
    ]
    if not statements:
        return
    with db.engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                logger.info("Applied LMS schema patch: %s", stmt)
            except Exception as exc:
                logger.warning("LMS schema patch skipped (%s): %s", stmt, exc)


def _add_indexes_if_missing(
    inspector,
    table_name: str,
    specs: tuple[tuple[tuple[str, ...], str, bool], ...],
) -> None:
    if table_name not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    with db.engine.begin() as conn:
        for columns, name, unique in specs:
            if name in existing:
                continue
            keyword = "UNIQUE INDEX" if unique else "INDEX"
            statement = f"CREATE {keyword} {name} ON {table_name} ({', '.join(columns)})"
            try:
                conn.execute(text(statement))
                logger.info("Applied LMS schema index: %s", statement)
            except Exception as exc:
                logger.warning("LMS schema index skipped (%s): %s", statement, exc)


def _slugify(name: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "category"


def _seed_course_categories_if_empty() -> None:
    from app.constants import MEDICAL_COURSE_CATEGORIES
    from app.models.course_model import CourseCategory

    if CourseCategory.query.count() > 0:
        return

    rows = []
    for i, name in enumerate(MEDICAL_COURSE_CATEGORIES):
        rows.append(
            CourseCategory(
                name=name,
                slug=_slugify(name),
                description=f"Medical learning courses in {name}.",
                sort_order=i,
                is_active=True,
            )
        )
    db.session.add_all(rows)
    db.session.commit()
    logger.info("Seeded %d course categories.", len(rows))


# Short speciality labels → LMS category names (UI filter chips use full names)
_SPECIALITY_CATEGORY_ALIASES = {
    "nursing": "nursing fundamentals",
    "emergency": "emergency medicine",
    "emergency care": "emergency medicine",
    "surgery": "surgical nursing",
    "infectious disease": "infection control",
    "mental health": "mental health nursing",
}


def _link_existing_courses_to_categories() -> None:
    """Best-effort: map Course.speciality → CourseCategory for older rows."""
    from app.models.course_model import Course, CourseCategory

    categories = {c.name.lower(): c for c in CourseCategory.query.all()}
    if not categories:
        return

    updated = 0
    for course in Course.query.filter(Course.category_id.is_(None)).all():
        key = (course.speciality or "").strip().lower()
        if not key:
            continue
        match = categories.get(key)
        if not match:
            alias = _SPECIALITY_CATEGORY_ALIASES.get(key)
            if alias:
                match = categories.get(alias)
        if not match:
            # Partial: "Nursing" matches "Nursing Fundamentals"
            for name, cat in categories.items():
                if key in name or name in key:
                    match = cat
                    break
        if match:
            course.category_id = match.id
            # Keep speciality aligned with category so UI filters match
            if course.speciality and course.speciality.strip().lower() != match.name.lower():
                if key in _SPECIALITY_CATEGORY_ALIASES or key != match.name.lower():
                    course.speciality = match.name
            updated += 1
    if updated:
        db.session.commit()
        logger.info("Linked %d existing course(s) to categories.", updated)


def _backfill_learning_booleans() -> None:
    """NULL booleans break filters (is_published=True) and JSON serialization."""
    from app.models.course_model import Course, Lesson

    changed = 0
    for course in Course.query.filter(Course.is_published.is_(None)).all():
        course.is_published = True
        changed += 1
    for course in Course.query.filter(Course.certificate_eligible.is_(None)).all():
        course.certificate_eligible = True
        changed += 1
    for lesson in Lesson.query.filter(Lesson.is_published.is_(None)).all():
        lesson.is_published = True
        changed += 1
    if changed:
        db.session.commit()
        logger.info("Backfilled %d learning boolean field(s).", changed)


def ensure_medical_teacher_schema() -> None:
    """Create AI Medical Teacher tables (books, chapters, processing jobs)."""
    try:
        from app.models.book_model import Book, Chapter, DocumentProcessingJob  # noqa: F401
        from app.models.rag_model import ChunkEmbedding, DocumentChunk  # noqa: F401
        from app.models.tutor_model import TutorMessage, TutorSession  # noqa: F401
        from app.models.adaptive_learning_model import LearningTopicMastery  # noqa: F401
        from app.models.learning_activity_model import LearningActivity  # noqa: F401

        Book.__table__.create(bind=db.engine, checkfirst=True)
        Chapter.__table__.create(bind=db.engine, checkfirst=True)
        DocumentProcessingJob.__table__.create(bind=db.engine, checkfirst=True)
        DocumentChunk.__table__.create(bind=db.engine, checkfirst=True)
        ChunkEmbedding.__table__.create(bind=db.engine, checkfirst=True)
        TutorSession.__table__.create(bind=db.engine, checkfirst=True)
        TutorMessage.__table__.create(bind=db.engine, checkfirst=True)
        LearningTopicMastery.__table__.create(bind=db.engine, checkfirst=True)
        LearningActivity.__table__.create(bind=db.engine, checkfirst=True)

        inspector = inspect(db.engine)
        _add_columns_if_missing(
            inspector,
            "tutor_sessions",
            (
                ("session_type", "VARCHAR(30) NOT NULL DEFAULT 'tutor'"),
                ("topic_id", "INT NULL"),
                ("difficulty", "VARCHAR(20) NULL"),
                ("current_step", "INT NOT NULL DEFAULT 0"),
                ("total_steps", "INT NOT NULL DEFAULT 0"),
                ("correct_answers", "INT NOT NULL DEFAULT 0"),
                ("incorrect_answers", "INT NOT NULL DEFAULT 0"),
                ("plan_json", "JSON NULL"),
                ("state_json", "JSON NULL"),
                ("completed_at", "DATETIME NULL"),
            ),
        )
        inspector = inspect(db.engine)
        _add_indexes_if_missing(
            inspector,
            "tutor_sessions",
            (
                (("session_type",), "ix_tutor_sessions_session_type", False),
                (("topic_id",), "ix_tutor_sessions_topic_id", False),
                (("user_id", "book_id", "session_type", "updated_at"), "ix_tutor_sessions_owner_book_type_updated", False),
            ),
        )

        inspector = inspect(db.engine)
        _add_columns_if_missing(
            inspector,
            "books",
            (
                ("storage_backend", "VARCHAR(40) NOT NULL DEFAULT 'local'"),
                ("storage_key", "VARCHAR(500) NULL"),
                ("rag_status", "VARCHAR(30) NULL"),
                ("rag_provider", "VARCHAR(40) NULL"),
                ("rag_model", "VARCHAR(120) NULL"),
                ("rag_chunk_count", "INT NULL"),
                ("rag_indexed_at", "DATETIME NULL"),
                ("rag_error", "VARCHAR(500) NULL"),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "books",
            (
                ("analysis_json", "JSON NULL"),
                ("parse_method", "VARCHAR(40) NULL"),
                ("chapter_count", "INT NULL"),
                ("parsed_at", "DATETIME NULL"),
            ),
        )
        with db.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE books SET storage_backend = 'local' "
                    "WHERE storage_backend IS NULL OR storage_backend = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE books SET storage_key = stored_filename "
                    "WHERE storage_key IS NULL OR storage_key = ''"
                )
            )
        logger.info(
            "Medical Teacher schema verified (documents, tutor, adaptive mastery, and learning activity)."
        )
    except Exception:
        logger.exception("Failed to ensure medical teacher schema")


def ensure_xray_reference_library_schema() -> None:
    """Create healthy X-ray reference library tables (legacy + production)."""
    try:
        from app.models.xray_reference_model import XrayReferenceImage  # noqa: F401
        from app.models.reference_xray_library_model import ReferenceXrayLibrary  # noqa: F401

        # Legacy catalog used by the interim reference manager (kept for migration)
        XrayReferenceImage.__table__.create(bind=db.engine, checkfirst=True)
        # Production Reference X-Ray Library (Module 1)
        ReferenceXrayLibrary.__table__.create(bind=db.engine, checkfirst=True)
        _ensure_reference_xray_library_columns()
        logger.info(
          "X-ray reference library schema verified "
          "(xray_reference_images, reference_xray_library)."
        )
    except Exception:
        logger.exception("Failed to ensure xray reference library schema")


def _ensure_reference_xray_library_columns() -> None:
    """Idempotent column add for reference_xray_library (MySQL / SQLite)."""
    inspector = inspect(db.engine)
    if "reference_xray_library" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("reference_xray_library")}
    # Future-proof: add any new operational columns without dropping data
    additions = {
        "mime_type": "VARCHAR(80) NULL",
        "file_size": "INTEGER NULL",
        "width": "INTEGER NULL",
        "height": "INTEGER NULL",
        "content_hash": "VARCHAR(64) NULL",
        "public_id": "VARCHAR(120) NULL",
    }
    for name, ddl in additions.items():
        if name in existing:
            continue
        try:
            with db.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE reference_xray_library ADD COLUMN {name} {ddl}"))
            logger.info("Added reference_xray_library.%s", name)
        except Exception:
            logger.exception("Could not add reference_xray_library.%s", name)
def ensure_platform_settings_schema() -> None:
    """Create platform_settings table for Admin Panel preferences (Module 11)."""
    try:
        from app.models.platform_setting_model import PlatformSetting  # noqa: F401

        PlatformSetting.__table__.create(bind=db.engine, checkfirst=True)
        logger.info("Platform settings schema verified (platform_settings).")
    except Exception:
        logger.exception("Failed to ensure platform settings schema")


def ensure_user_previous_role_schema() -> None:
    """Add users.previous_role for Admin Panel promote/demote restore."""
    try:
        inspector = inspect(db.engine)
        if "users" not in inspector.get_table_names():
            return
        existing = {col["name"] for col in inspector.get_columns("users")}
        if "previous_role" in existing:
            return
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN previous_role VARCHAR(30) NULL"))
        logger.info("Added users.previous_role")
    except Exception:
        logger.exception("Could not add users.previous_role")


def ensure_body_systems_hub_schema() -> None:
    """Phase 1 — AI Human Body Systems Learning Hub tables + seed catalog.

    Additive only. Reuses courses / lessons / quizzes / clinical_cases via junction
    tables. Does not rewrite the existing LMS.
    """
    try:
        from app.models.body_system_model import (
            BODY_SYSTEM_SEED,
            ORGAN_SEED,
            BodySystem,
            BodySystemCourse,
            BodySystemProgress,
            BodySystemQuiz,
            HubCertificate,
            HubDisease,
            HubDiseaseClinicalCase,
            HubFlashcard,
            HubFlashcardFavorite,
            HubRecommendation,
            Organ,
            OrganLesson,
        )

        for table in (
            BodySystem.__table__,
            Organ.__table__,
            HubDisease.__table__,
            BodySystemCourse.__table__,
            BodySystemQuiz.__table__,
            OrganLesson.__table__,
            HubDiseaseClinicalCase.__table__,
            HubFlashcard.__table__,
            HubFlashcardFavorite.__table__,
            BodySystemProgress.__table__,
            HubRecommendation.__table__,
            HubCertificate.__table__,
        ):
            table.create(bind=db.engine, checkfirst=True)

        inspector = inspect(db.engine)
        _add_columns_if_missing(
            inspector,
            "body_systems",
            (
                ("long_description", "TEXT NULL"),
                ("emoji", "VARCHAR(16) NULL"),
                ("illustration_url", "VARCHAR(500) NULL"),
                ("difficulty", "VARCHAR(20) NULL"),
                ("estimated_minutes", "INT NULL"),
                ("lesson_count", "INT NULL"),
                ("is_published", "BOOLEAN NULL"),
                ("category_id", "INT NULL"),
                ("default_course_id", "INT NULL"),
                ("meta_json", "JSON NULL"),
                ("updated_at", "DATETIME NULL"),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "organs",
            (
                ("overview", "TEXT NULL"),
                ("location", "VARCHAR(120) NULL"),
                ("region_key", "VARCHAR(80) NULL"),
                ("illustration_url", "VARCHAR(500) NULL"),
                ("animation_key", "VARCHAR(80) NULL"),
                ("content_json", "JSON NULL"),
                ("learning_objectives", "JSON NULL"),
                ("is_published", "BOOLEAN NULL"),
                ("updated_at", "DATETIME NULL"),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "hub_flashcard_favorites",
            (
                ("ease_factor", "FLOAT NULL"),
                ("interval_days", "INT NULL"),
                ("repetitions", "INT NULL"),
                ("next_review_at", "DATETIME NULL"),
                ("last_reviewed_at", "DATETIME NULL"),
                ("status", "VARCHAR(30) NULL"),
                ("correct_count", "INT NULL"),
                ("incorrect_count", "INT NULL"),
                ("review_count", "INT NULL"),
                ("last_rating", "VARCHAR(30) NULL"),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "hub_flashcards",
            (
                ("owner_user_id", "INT NULL"),
                ("book_id", "INT NULL"),
                ("course_id", "INT NULL"),
                ("module_id", "INT NULL"),
                ("topic_id", "INT NULL"),
                ("source_json", "JSON NULL"),
                ("source_hash", "VARCHAR(64) NULL"),
                ("generation_hash", "VARCHAR(64) NULL"),
                ("origin", "VARCHAR(40) NULL"),
                ("generation_method", "VARCHAR(40) NULL"),
                ("generated_at", "DATETIME NULL"),
            ),
        )
        inspector = inspect(db.engine)
        _add_indexes_if_missing(
            inspector,
            "hub_flashcards",
            (
                (("book_id", "owner_user_id"), "ix_hub_flashcards_book_owner", False),
                (("book_id", "lesson_id"), "ix_hub_flashcards_book_lesson", False),
                (("topic_id", "card_level"), "ix_hub_flashcards_topic_level", False),
                (("generation_hash",), "ix_hub_flashcards_generation_hash", False),
                (("origin",), "ix_hub_flashcards_origin", False),
            ),
        )
        _add_indexes_if_missing(
            inspector,
            "hub_flashcard_favorites",
            (
                (("user_id", "status"), "ix_hub_flashcard_reviews_user_status", False),
                (("user_id", "next_review_at"), "ix_hub_flashcard_reviews_user_due", False),
            ),
        )
        _add_columns_if_missing(
            inspector,
            "clinical_cases",
            (("content_json", "JSON NULL"),),
        )

        # Seed body systems (idempotent by slug)
        existing_slugs = {
            row.slug for row in BodySystem.query.with_entities(BodySystem.slug).all()
        }
        created_systems = 0
        for item in BODY_SYSTEM_SEED:
            if item["slug"] in existing_slugs:
                continue
            db.session.add(
                BodySystem(
                    slug=item["slug"],
                    name=item["name"],
                    short_description=item["short_description"],
                    icon=item["icon"],
                    emoji=item.get("emoji"),
                    difficulty=item.get("difficulty") or "intermediate",
                    estimated_minutes=int(item.get("estimated_minutes") or 120),
                    sort_order=int(item.get("sort_order") or 0),
                    is_active=True,
                    is_published=True,
                )
            )
            created_systems += 1
        if created_systems:
            db.session.commit()
            logger.info("Seeded %s body systems for Learning Hub", created_systems)

        # Seed starter organs (idempotent by system+slug)
        from app.services.body_systems.organ_content import (
            apply_organ_content,
            get_organ_content,
            needs_phase4_enrichment,
        )

        systems_by_slug = {s.slug: s for s in BodySystem.query.all()}
        created_organs = 0
        for slug, name, system_slug, location, sort_order in ORGAN_SEED:
            system = systems_by_slug.get(system_slug)
            if not system:
                continue
            exists = Organ.query.filter_by(body_system_id=system.id, slug=slug).first()
            if exists:
                continue
            pack = get_organ_content(slug)
            organ = Organ(
                body_system_id=system.id,
                slug=slug,
                name=name,
                short_description=(
                    pack["short_description"]
                    if pack
                    else f"Educational overview of the {name.lower()}."
                ),
                location=location,
                region_key=slug,
                sort_order=sort_order,
                is_active=True,
                is_published=True,
                content_json={
                    "overview": None,
                    "functions": [],
                    "clinical_importance": None,
                    "safety": {
                        "educational_only": True,
                        "not_a_diagnosis": True,
                    },
                },
            )
            if pack:
                apply_organ_content(organ, pack)
            db.session.add(organ)
            created_organs += 1
        if created_organs:
            db.session.commit()
            logger.info("Seeded %s organs for Learning Hub", created_organs)

        # Phase 4 — enrich existing starter organs with full educational pages
        enriched = 0
        starter_slugs = [item[0] for item in ORGAN_SEED]
        for organ in Organ.query.filter(Organ.slug.in_(starter_slugs)).all():
            pack = get_organ_content(organ.slug)
            if not pack or not needs_phase4_enrichment(organ):
                continue
            apply_organ_content(organ, pack)
            enriched += 1
        if enriched:
            db.session.commit()
            logger.info("Enriched %s organs with Phase 4 educational content", enriched)

        logger.info("Body Systems Learning Hub schema verified.")
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.exception("Failed to ensure body systems hub schema")
