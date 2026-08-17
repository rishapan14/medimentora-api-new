"""Admin Simulations management (Module 9)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_

from app.extensions import db
from app.models.simulation_model import Simulation, SimulationAttempt
from app.validations.simulation_validation import validate_simulation

logger = logging.getLogger(__name__)


class AdminSimulationService:
  """CRUD for clinical simulation scenarios in the Admin Panel."""

  @classmethod
  def stats(cls) -> dict[str, Any]:
    total = Simulation.query.count()
    active = Simulation.query.filter(
      or_(Simulation.is_active.is_(True), Simulation.is_active.is_(None))
    ).count()
    inactive = total - active
    attempts = SimulationAttempt.query.count()

    by_difficulty: dict[str, int] = {}
    for diff, count in (
      db.session.query(Simulation.difficulty, func.count(Simulation.id))
      .group_by(Simulation.difficulty)
      .all()
    ):
      by_difficulty[str(diff or "medium")] = int(count)

    return {
      "simulations": total,
      "active": active,
      "inactive": inactive,
      "attempts": attempts,
      "by_difficulty": by_difficulty,
    }

  @classmethod
  def _admin_row(cls, sim: Simulation) -> dict[str, Any]:
    payload = sim.to_dict(include_answers=True)
    payload["attempt_count"] = sim.attempts.count()
    return payload

  @classmethod
  def list_simulations(
    cls,
    *,
    q: str | None = None,
    difficulty: str | None = None,
    speciality: str | None = None,
    is_active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
  ) -> dict[str, Any]:
    query = Simulation.query

    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        or_(
          Simulation.title.ilike(like),
          Simulation.scenario.ilike(like),
          Simulation.speciality.ilike(like),
          Simulation.correct_diagnosis.ilike(like),
        )
      )

    if difficulty:
      query = query.filter(Simulation.difficulty == difficulty.strip().lower())

    if speciality:
      query = query.filter(Simulation.speciality.ilike(f"%{speciality.strip()}%"))

    if is_active is True:
      query = query.filter(or_(Simulation.is_active.is_(True), Simulation.is_active.is_(None)))
    elif is_active is False:
      query = query.filter(Simulation.is_active.is_(False))

    total = query.count()
    rows = (
      query.order_by(Simulation.created_at.desc(), Simulation.id.desc())
      .offset(max(0, offset))
      .limit(min(max(int(limit), 1), 200))
      .all()
    )

    return {
      "simulations": [cls._admin_row(s) for s in rows],
      "total": total,
      "offset": offset,
      "limit": limit,
      "stats": cls.stats(),
    }

  @classmethod
  def get_simulation(cls, simulation_id: int) -> dict[str, Any] | None:
    sim = db.session.get(Simulation, simulation_id)
    if not sim:
      return None
    return cls._admin_row(sim)

  @classmethod
  def create_simulation(cls, data: dict[str, Any] | None) -> dict[str, Any]:
    errors = validate_simulation(data)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    assert data is not None
    diagnosis_options = data.get("diagnosis_options") or []
    treatment_options = data.get("treatment_options") or []
    correct_dx = str(data["correct_diagnosis"]).strip()
    correct_tx = str(data["correct_treatment"]).strip()

    if diagnosis_options and correct_dx not in [str(o).strip() for o in diagnosis_options]:
      return {
        "success": False,
        "message": "correct_diagnosis must match one of diagnosis_options when options are set.",
        "error_code": "validation_error",
        "data": {"errors": ["correct_diagnosis must match one of diagnosis_options."]},
      }
    if treatment_options and correct_tx not in [str(o).strip() for o in treatment_options]:
      return {
        "success": False,
        "message": "correct_treatment must match one of treatment_options when options are set.",
        "error_code": "validation_error",
        "data": {"errors": ["correct_treatment must match one of treatment_options."]},
      }

    try:
      sim = Simulation(
        title=str(data["title"]).strip(),
        scenario=str(data["scenario"]).strip(),
        patient_data=data.get("patient_data") or {},
        correct_diagnosis=correct_dx,
        correct_treatment=correct_tx,
        diagnosis_options=diagnosis_options,
        treatment_options=treatment_options,
        difficulty=(data.get("difficulty") or "medium").lower(),
        speciality=data.get("speciality"),
        max_score=int(data.get("max_score") or 100),
        is_active=bool(data.get("is_active", True)),
      )
      db.session.add(sim)
      db.session.commit()
      return {
        "success": True,
        "message": "Simulation created.",
        "data": {"simulation": cls._admin_row(sim)},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin create simulation failed")
      return {
        "success": False,
        "message": "Could not create simulation.",
        "error_code": "create_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def update_simulation(cls, simulation_id: int, data: dict[str, Any] | None) -> dict[str, Any]:
    sim = db.session.get(Simulation, simulation_id)
    if not sim:
      return {"success": False, "message": "Simulation not found.", "error_code": "not_found"}

    errors = validate_simulation(data, partial=True)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    assert data is not None
    diagnosis_options = data.get("diagnosis_options", sim.diagnosis_options) or []
    treatment_options = data.get("treatment_options", sim.treatment_options) or []
    correct_dx = data.get("correct_diagnosis", sim.correct_diagnosis)
    correct_tx = data.get("correct_treatment", sim.correct_treatment)

    if correct_dx is not None and diagnosis_options:
      if str(correct_dx).strip() not in [str(o).strip() for o in diagnosis_options]:
        return {
          "success": False,
          "message": "correct_diagnosis must match one of diagnosis_options when options are set.",
          "error_code": "validation_error",
          "data": {"errors": ["correct_diagnosis must match one of diagnosis_options."]},
        }
    if correct_tx is not None and treatment_options:
      if str(correct_tx).strip() not in [str(o).strip() for o in treatment_options]:
        return {
          "success": False,
          "message": "correct_treatment must match one of treatment_options when options are set.",
          "error_code": "validation_error",
          "data": {"errors": ["correct_treatment must match one of treatment_options."]},
        }

    try:
      for field in (
        "title",
        "scenario",
        "patient_data",
        "correct_diagnosis",
        "correct_treatment",
        "diagnosis_options",
        "treatment_options",
        "difficulty",
        "speciality",
        "max_score",
        "is_active",
      ):
        if field in data:
          value = data[field]
          if field in ("title", "scenario", "correct_diagnosis", "correct_treatment") and isinstance(
            value, str
          ):
            value = value.strip()
          if field == "difficulty" and value:
            value = str(value).lower()
          setattr(sim, field, value)
      db.session.commit()
      return {
        "success": True,
        "message": "Simulation updated.",
        "data": {"simulation": cls._admin_row(sim)},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin update simulation failed id=%s", simulation_id)
      return {
        "success": False,
        "message": "Could not update simulation.",
        "error_code": "update_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def set_active(cls, simulation_id: int, *, active: bool) -> dict[str, Any]:
    return cls.update_simulation(simulation_id, {"is_active": bool(active)})

  @classmethod
  def delete_simulation(cls, simulation_id: int) -> dict[str, Any]:
    sim = db.session.get(Simulation, simulation_id)
    if not sim:
      return {"success": False, "message": "Simulation not found.", "error_code": "not_found"}
    try:
      db.session.delete(sim)
      db.session.commit()
      logger.info("Admin deleted simulation id=%s", simulation_id)
      return {"success": True, "message": "Simulation deleted."}
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin delete simulation failed id=%s", simulation_id)
      return {
        "success": False,
        "message": "Could not delete simulation.",
        "error_code": "delete_failed",
        "data": {"detail": str(exc)},
      }
