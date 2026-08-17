from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import learning_controller as ctrl
from app.middleware import roles_required
from app.constants import ROLE_ADMIN, ROLE_DOCTOR

learning_bp = Blueprint("learning", __name__, url_prefix="/api/learning")

# Categories
learning_bp.add_url_rule("/categories", view_func=jwt_required()(ctrl.list_categories), methods=["GET"])

# Courses
learning_bp.add_url_rule("/courses", view_func=jwt_required()(ctrl.list_courses), methods=["GET"])
learning_bp.add_url_rule("/courses/<int:course_id>", view_func=jwt_required()(ctrl.get_course), methods=["GET"])
learning_bp.add_url_rule(
  "/courses/<int:course_id>/enroll",
  view_func=jwt_required()(ctrl.enroll_course),
  methods=["POST"],
)
learning_bp.add_url_rule(
  "/courses",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.create_course),
  methods=["POST"],
)
learning_bp.add_url_rule(
  "/courses/<int:course_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.update_course),
  methods=["PUT"],
)
learning_bp.add_url_rule(
  "/courses/<int:course_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.delete_course),
  methods=["DELETE"],
)

# Lessons
learning_bp.add_url_rule("/courses/<int:course_id>/lessons", view_func=jwt_required()(ctrl.list_lessons), methods=["GET"])
learning_bp.add_url_rule("/lessons/<int:lesson_id>", view_func=jwt_required()(ctrl.get_lesson), methods=["GET"])
learning_bp.add_url_rule(
  "/lessons",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.create_lesson),
  methods=["POST"],
)
learning_bp.add_url_rule(
  "/lessons/<int:lesson_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.update_lesson),
  methods=["PUT"],
)
learning_bp.add_url_rule(
  "/lessons/<int:lesson_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.delete_lesson),
  methods=["DELETE"],
)

# Bookmarks
learning_bp.add_url_rule("/bookmarks", view_func=jwt_required()(ctrl.list_bookmarks), methods=["GET"])
learning_bp.add_url_rule("/lessons/<int:lesson_id>/bookmark", view_func=jwt_required()(ctrl.add_bookmark), methods=["POST"])
learning_bp.add_url_rule("/lessons/<int:lesson_id>/bookmark", view_func=jwt_required()(ctrl.remove_bookmark), methods=["DELETE"])

# Completed lessons / progress
learning_bp.add_url_rule("/lessons/<int:lesson_id>/complete", view_func=jwt_required()(ctrl.complete_lesson), methods=["POST"])
learning_bp.add_url_rule("/completed-lessons", view_func=jwt_required()(ctrl.list_completed_lessons), methods=["GET"])
learning_bp.add_url_rule("/course-progress", view_func=jwt_required()(ctrl.list_course_progress), methods=["GET"])

# Recommendations & weak topics
learning_bp.add_url_rule("/recommendations", view_func=jwt_required()(ctrl.list_recommendations), methods=["GET"])
learning_bp.add_url_rule("/weak-topics", view_func=jwt_required()(ctrl.weak_topics), methods=["GET"])

# ---------------------------------------------------------------------------
# Phase 2 — AI Human Body Systems Learning Hub
# ---------------------------------------------------------------------------
from app.controllers import body_system_controller as hub_ctrl

learning_bp.add_url_rule(
  "/body-systems",
  view_func=jwt_required()(hub_ctrl.list_body_systems),
  methods=["GET"],
  endpoint="learning_list_body_systems",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>",
  view_func=jwt_required()(hub_ctrl.get_body_system),
  methods=["GET"],
  endpoint="learning_get_body_system",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/organs",
  view_func=jwt_required()(hub_ctrl.list_system_organs),
  methods=["GET"],
  endpoint="learning_list_system_organs",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/quizzes",
  view_func=jwt_required()(hub_ctrl.list_system_hub_quizzes),
  methods=["GET"],
  endpoint="learning_list_system_hub_quizzes",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/quizzes/generate",
  view_func=jwt_required()(hub_ctrl.generate_system_hub_quiz),
  methods=["POST"],
  endpoint="learning_generate_system_hub_quiz",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/cases",
  view_func=jwt_required()(hub_ctrl.list_system_hub_cases),
  methods=["GET"],
  endpoint="learning_list_system_hub_cases",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/cases/generate",
  view_func=jwt_required()(hub_ctrl.generate_system_hub_cases),
  methods=["POST"],
  endpoint="learning_generate_system_hub_cases",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/diseases",
  view_func=jwt_required()(hub_ctrl.list_system_diseases),
  methods=["GET"],
  endpoint="learning_list_system_diseases",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/start",
  view_func=jwt_required()(hub_ctrl.start_body_system_progress),
  methods=["POST"],
  endpoint="learning_start_body_system",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/progress",
  view_func=jwt_required()(hub_ctrl.get_body_system_progress),
  methods=["GET"],
  endpoint="learning_get_body_system_progress",
)
learning_bp.add_url_rule(
  "/body-systems/<string:slug>/progress",
  view_func=jwt_required()(hub_ctrl.update_body_system_progress),
  methods=["PUT", "PATCH"],
  endpoint="learning_update_body_system_progress",
)
learning_bp.add_url_rule(
  "/organs/<string:slug>",
  view_func=jwt_required()(hub_ctrl.get_organ),
  methods=["GET"],
  endpoint="learning_get_organ",
)
learning_bp.add_url_rule(
  "/diseases/<string:slug>",
  view_func=jwt_required()(hub_ctrl.get_disease),
  methods=["GET"],
  endpoint="learning_get_disease",
)
learning_bp.add_url_rule(
  "/hub/search",
  view_func=jwt_required()(hub_ctrl.hub_search),
  methods=["GET"],
  endpoint="learning_hub_search",
)
learning_bp.add_url_rule(
  "/hub/recommendations",
  view_func=jwt_required()(hub_ctrl.list_hub_recommendations),
  methods=["GET"],
  endpoint="learning_hub_recommendations",
)
learning_bp.add_url_rule(
  "/hub/progress",
  view_func=jwt_required()(hub_ctrl.get_hub_progress),
  methods=["GET"],
  endpoint="learning_hub_progress",
)
learning_bp.add_url_rule(
  "/hub/certificates",
  view_func=jwt_required()(hub_ctrl.list_hub_certificates),
  methods=["GET"],
  endpoint="learning_hub_certificates",
)
learning_bp.add_url_rule(
  "/hub/certificates/<int:certificate_id>",
  view_func=jwt_required()(hub_ctrl.get_hub_certificate),
  methods=["GET"],
  endpoint="learning_hub_certificate_detail",
)
learning_bp.add_url_rule(
  "/hub/certificates/<int:certificate_id>/download",
  view_func=jwt_required()(hub_ctrl.download_hub_certificate),
  methods=["GET"],
  endpoint="learning_hub_certificate_download",
)
learning_bp.add_url_rule(
  "/hub/flashcards",
  view_func=jwt_required()(hub_ctrl.list_hub_flashcards),
  methods=["GET"],
  endpoint="learning_hub_flashcards",
)
learning_bp.add_url_rule(
  "/hub/flashcards/generate",
  view_func=jwt_required()(hub_ctrl.generate_hub_flashcards),
  methods=["POST"],
  endpoint="learning_hub_flashcards_generate",
)
learning_bp.add_url_rule(
  "/hub/flashcards/favorites",
  view_func=jwt_required()(hub_ctrl.list_hub_flashcard_favorites),
  methods=["GET"],
  endpoint="learning_hub_flashcards_favorites",
)
learning_bp.add_url_rule(
  "/hub/flashcards/<int:flashcard_id>/favorite",
  view_func=jwt_required()(hub_ctrl.favorite_hub_flashcard),
  methods=["POST"],
  endpoint="learning_hub_flashcard_favorite",
)
learning_bp.add_url_rule(
  "/hub/flashcards/<int:flashcard_id>/favorite",
  view_func=jwt_required()(hub_ctrl.unfavorite_hub_flashcard),
  methods=["DELETE"],
  endpoint="learning_hub_flashcard_unfavorite",
)
learning_bp.add_url_rule(
  "/hub/explorer",
  view_func=jwt_required()(hub_ctrl.get_hub_explorer),
  methods=["GET"],
  endpoint="learning_hub_explorer",
)
learning_bp.add_url_rule(
  "/hub/tutor/modes",
  view_func=jwt_required()(hub_ctrl.list_hub_tutor_modes),
  methods=["GET"],
  endpoint="learning_hub_tutor_modes",
)
learning_bp.add_url_rule(
  "/hub/tutor",
  view_func=jwt_required()(hub_ctrl.hub_ai_tutor),
  methods=["POST"],
  endpoint="learning_hub_tutor",
)
