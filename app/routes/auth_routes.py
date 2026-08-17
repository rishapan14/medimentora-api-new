from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import auth_controller as ctrl

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

auth_bp.add_url_rule("/register", view_func=ctrl.register, methods=["POST"])
auth_bp.add_url_rule("/login", view_func=ctrl.login, methods=["POST"])
auth_bp.add_url_rule("/refresh", view_func=jwt_required(refresh=True)(ctrl.refresh), methods=["POST"])
auth_bp.add_url_rule("/forgot-password", view_func=ctrl.forgot_password, methods=["POST"])
auth_bp.add_url_rule("/reset-password", view_func=ctrl.reset_password, methods=["POST"])
auth_bp.add_url_rule("/profile", view_func=jwt_required()(ctrl.profile), methods=["GET", "PUT"])
auth_bp.add_url_rule("/logout", view_func=jwt_required()(ctrl.logout), methods=["POST"])
