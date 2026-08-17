from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import progress_controller as ctrl

progress_bp = Blueprint("progress", __name__, url_prefix="/api/progress")

progress_bp.add_url_rule("", view_func=jwt_required()(ctrl.get_progress), methods=["GET"])
progress_bp.add_url_rule("/dashboard", view_func=jwt_required()(ctrl.dashboard), methods=["GET"])
progress_bp.add_url_rule(
  "/learning-dashboard",
  view_func=jwt_required()(ctrl.learning_dashboard),
  methods=["GET"],
)
progress_bp.add_url_rule("/achievements", view_func=jwt_required()(ctrl.achievements), methods=["GET"])
