from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import simulation_controller as ctrl
from app.constants import ROLE_ADMIN, ROLE_DOCTOR
from app.middleware import roles_required

simulation_bp = Blueprint("simulations", __name__, url_prefix="/api/simulations")

simulation_bp.add_url_rule("", view_func=jwt_required()(ctrl.list_simulations), methods=["GET"])
simulation_bp.add_url_rule("/history", view_func=jwt_required()(ctrl.attempt_history), methods=["GET"])
simulation_bp.add_url_rule("/<int:simulation_id>", view_func=jwt_required()(ctrl.get_simulation), methods=["GET"])
simulation_bp.add_url_rule(
  "",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.create_simulation),
  methods=["POST"],
)
simulation_bp.add_url_rule(
  "/<int:simulation_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.update_simulation),
  methods=["PUT"],
)
simulation_bp.add_url_rule(
  "/<int:simulation_id>",
  view_func=roles_required(ROLE_ADMIN, ROLE_DOCTOR)(ctrl.delete_simulation),
  methods=["DELETE"],
)
simulation_bp.add_url_rule(
  "/<int:simulation_id>/submit",
  view_func=jwt_required()(ctrl.submit_attempt),
  methods=["POST"],
)
