from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import quiz_controller as ctrl
from app.constants import ROLE_ADMIN, ROLE_DOCTOR
from app.middleware import roles_required

quiz_bp = Blueprint("quizzes", __name__, url_prefix="/api/quizzes")

quiz_bp.add_url_rule("", view_func=jwt_required()(ctrl.list_quizzes), methods=["GET"])
quiz_bp.add_url_rule("/leaderboard", view_func=jwt_required()(ctrl.leaderboard), methods=["GET"])
quiz_bp.add_url_rule("/results", view_func=jwt_required()(ctrl.my_results), methods=["GET"])
quiz_bp.add_url_rule("/<int:quiz_id>", view_func=jwt_required()(ctrl.get_quiz), methods=["GET"])
quiz_bp.add_url_rule(
  "",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.create_quiz),
  methods=["POST"],
)
quiz_bp.add_url_rule(
  "/<int:quiz_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.update_quiz),
  methods=["PUT"],
)
quiz_bp.add_url_rule(
  "/<int:quiz_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.delete_quiz),
  methods=["DELETE"],
)
quiz_bp.add_url_rule(
  "/<int:quiz_id>/questions",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.create_question),
  methods=["POST"],
)
quiz_bp.add_url_rule(
  "/questions/<int:question_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.update_question),
  methods=["PUT"],
)
quiz_bp.add_url_rule(
  "/questions/<int:question_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.delete_question),
  methods=["DELETE"],
)
quiz_bp.add_url_rule("/<int:quiz_id>/submit", view_func=jwt_required()(ctrl.submit_quiz), methods=["POST"])
