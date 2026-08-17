from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import notification_controller as ctrl
from app.constants import ROLE_ADMIN
from app.middleware import roles_required

notification_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")

notification_bp.add_url_rule("", view_func=jwt_required()(ctrl.list_notifications), methods=["GET"])
notification_bp.add_url_rule("/read-all", view_func=jwt_required()(ctrl.mark_all_read), methods=["PUT"])
notification_bp.add_url_rule("/<int:notification_id>/read", view_func=jwt_required()(ctrl.mark_read), methods=["PUT"])
notification_bp.add_url_rule("/<int:notification_id>", view_func=jwt_required()(ctrl.delete_notification), methods=["DELETE"])
notification_bp.add_url_rule("/learning-reminder", view_func=jwt_required()(ctrl.create_learning_reminder), methods=["POST"])
notification_bp.add_url_rule("/quiz-reminder", view_func=jwt_required()(ctrl.create_quiz_reminder), methods=["POST"])
notification_bp.add_url_rule(
  "",
  view_func=roles_required(ROLE_ADMIN)(ctrl.create_notification),
  methods=["POST"],
)
