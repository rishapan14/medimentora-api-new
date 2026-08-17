from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import certificate_controller as ctrl

certificate_bp = Blueprint("certificates", __name__, url_prefix="/api/certificates")

certificate_bp.add_url_rule("", view_func=jwt_required()(ctrl.list_certificates), methods=["GET"])
certificate_bp.add_url_rule("/generate", view_func=jwt_required()(ctrl.generate_certificate), methods=["POST"])
certificate_bp.add_url_rule("/<int:certificate_id>", view_func=jwt_required()(ctrl.get_certificate), methods=["GET"])
certificate_bp.add_url_rule("/<int:certificate_id>/download", view_func=jwt_required()(ctrl.download_certificate), methods=["GET"])
