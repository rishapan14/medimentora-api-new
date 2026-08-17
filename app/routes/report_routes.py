from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import report_controller as ctrl

report_bp = Blueprint("reports", __name__, url_prefix="/api/reports")

report_bp.add_url_rule("/upload", view_func=jwt_required()(ctrl.upload_multiple), methods=["POST"])
report_bp.add_url_rule("/upload/pdf", view_func=jwt_required()(ctrl.upload_pdf), methods=["POST"])
report_bp.add_url_rule("/upload/image", view_func=jwt_required()(ctrl.upload_image), methods=["POST"])
report_bp.add_url_rule("", view_func=jwt_required()(ctrl.save_report), methods=["POST"])
report_bp.add_url_rule("", view_func=jwt_required()(ctrl.list_reports), methods=["GET"])
report_bp.add_url_rule("/history", view_func=jwt_required()(ctrl.report_history), methods=["GET"])
report_bp.add_url_rule("/<int:report_id>", view_func=jwt_required()(ctrl.get_report), methods=["GET"])
report_bp.add_url_rule("/<int:report_id>", view_func=jwt_required()(ctrl.delete_report), methods=["DELETE"])
report_bp.add_url_rule("/<int:report_id>/extract", view_func=jwt_required()(ctrl.extract_text), methods=["POST"])
