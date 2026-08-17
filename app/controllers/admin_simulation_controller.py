"""Admin APIs for Simulations management (Module 9)."""

from __future__ import annotations

from flask import request

from app.helpers.response import error_response, success_response
from app.services.admin.simulation_admin_service import AdminSimulationService


def _status_for(code: str | None) -> int:
  if code == "not_found":
    return 404
  if code == "validation_error":
    return 400
  return 422


def _parse_bool(raw, default=None):
  if raw is None:
    return default
  return str(raw).lower() in ("1", "true", "yes", "active")


def admin_list_simulations():
  """GET /api/admin/simulations"""
  try:
    limit = int(request.args.get("limit") or 50)
  except (TypeError, ValueError):
    limit = 50
  try:
    offset = int(request.args.get("offset") or 0)
  except (TypeError, ValueError):
    offset = 0

  active_param = request.args.get("is_active") or request.args.get("active")
  is_active = _parse_bool(active_param) if active_param is not None else None
  if active_param is not None and str(active_param).lower() in ("0", "false", "no", "inactive"):
    is_active = False

  payload = AdminSimulationService.list_simulations(
    q=request.args.get("q") or request.args.get("search"),
    difficulty=request.args.get("difficulty"),
    speciality=request.args.get("speciality"),
    is_active=is_active,
    limit=limit,
    offset=offset,
  )
  return success_response("Simulations retrieved.", payload)


def admin_get_simulation(simulation_id: int):
  """GET /api/admin/simulations/<id>"""
  sim = AdminSimulationService.get_simulation(simulation_id)
  if not sim:
    return error_response("Simulation not found.", 404)
  return success_response("Simulation retrieved.", {"simulation": sim})


def admin_create_simulation():
  """POST /api/admin/simulations"""
  result = AdminSimulationService.create_simulation(request.get_json(silent=True))
  if not result.get("success"):
    return error_response(
      result.get("message") or "Create failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {}, 201)


def admin_update_simulation(simulation_id: int):
  """PUT/PATCH /api/admin/simulations/<id>"""
  result = AdminSimulationService.update_simulation(
    simulation_id, request.get_json(silent=True) or {}
  )
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_set_simulation_active(simulation_id: int):
  """POST /api/admin/simulations/<id>/status  body: { is_active: bool }"""
  body = request.get_json(silent=True) or {}
  if "is_active" not in body and "active" not in body:
    return error_response("is_active is required.", 400)
  active = bool(body.get("is_active") if "is_active" in body else body.get("active"))
  result = AdminSimulationService.set_active(simulation_id, active=active)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_delete_simulation(simulation_id: int):
  """DELETE /api/admin/simulations/<id>"""
  result = AdminSimulationService.delete_simulation(simulation_id)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Delete failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"])
