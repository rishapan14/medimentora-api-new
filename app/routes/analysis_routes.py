from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import analysis_controller as ctrl

analysis_bp = Blueprint("analysis", __name__, url_prefix="/api/analysis")

analysis_bp.add_url_rule("", view_func=jwt_required()(ctrl.analyze_report), methods=["POST"])
analysis_bp.add_url_rule("", view_func=jwt_required()(ctrl.list_analyses), methods=["GET"])
analysis_bp.add_url_rule("/<int:analysis_id>", view_func=jwt_required()(ctrl.get_analysis), methods=["GET"])
analysis_bp.add_url_rule("/<int:analysis_id>", view_func=jwt_required()(ctrl.delete_analysis), methods=["DELETE"])
