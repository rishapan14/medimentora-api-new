from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import clinical_case_controller as ctrl
from app.constants import ROLE_ADMIN, ROLE_DOCTOR
from app.middleware import roles_required

clinical_case_bp = Blueprint("clinical_cases", __name__, url_prefix="/api/clinical-cases")

clinical_case_bp.add_url_rule("", view_func=jwt_required()(ctrl.list_cases), methods=["GET"])
clinical_case_bp.add_url_rule("/favorites", view_func=jwt_required()(ctrl.list_favorites), methods=["GET"])
clinical_case_bp.add_url_rule("/<int:case_id>", view_func=jwt_required()(ctrl.get_case), methods=["GET"])
clinical_case_bp.add_url_rule(
  "",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.create_case),
  methods=["POST"],
)
clinical_case_bp.add_url_rule(
  "/<int:case_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.update_case),
  methods=["PUT"],
)
clinical_case_bp.add_url_rule(
  "/<int:case_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.delete_case),
  methods=["DELETE"],
)
clinical_case_bp.add_url_rule("/<int:case_id>/favorite", view_func=jwt_required()(ctrl.favorite_case), methods=["POST"])
clinical_case_bp.add_url_rule("/<int:case_id>/favorite", view_func=jwt_required()(ctrl.unfavorite_case), methods=["DELETE"])
