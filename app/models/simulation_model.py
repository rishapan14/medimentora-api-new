from app.extensions import db
from app.utils import utc_now


class Simulation(db.Model):
  """Patient simulation scenario."""

  __tablename__ = "simulations"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  title = db.Column(db.String(200), nullable=False)
  scenario = db.Column(db.Text, nullable=False)
  patient_data = db.Column(db.JSON, nullable=True)
  correct_diagnosis = db.Column(db.String(200), nullable=False)
  correct_treatment = db.Column(db.Text, nullable=False)
  diagnosis_options = db.Column(db.JSON, nullable=True)
  treatment_options = db.Column(db.JSON, nullable=True)
  difficulty = db.Column(db.String(20), default="medium")
  speciality = db.Column(db.String(100), nullable=True)
  max_score = db.Column(db.Integer, default=100)
  is_active = db.Column(db.Boolean, default=True)
  created_at = db.Column(db.DateTime, default=utc_now)

  attempts = db.relationship("SimulationAttempt", back_populates="simulation", lazy="dynamic", cascade="all, delete-orphan")

  def to_dict(self, include_answers=False):
    data = {
      "id": self.id,
      "title": self.title,
      "scenario": self.scenario,
      "patient_data": self.patient_data or {},
      "diagnosis_options": self.diagnosis_options or [],
      "treatment_options": self.treatment_options or [],
      "difficulty": self.difficulty,
      "speciality": self.speciality,
      "max_score": self.max_score,
      "is_active": self.is_active,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
    if include_answers:
      data["correct_diagnosis"] = self.correct_diagnosis
      data["correct_treatment"] = self.correct_treatment
    return data


class SimulationAttempt(db.Model):
  """User attempt history for a simulation."""

  __tablename__ = "simulation_attempts"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  simulation_id = db.Column(db.Integer, db.ForeignKey("simulations.id"), nullable=False, index=True)
  diagnosis_selected = db.Column(db.String(200), nullable=True)
  treatment_selected = db.Column(db.Text, nullable=True)
  ai_feedback = db.Column(db.Text, nullable=True)
  score = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)

  user = db.relationship("User", back_populates="simulation_attempts")
  simulation = db.relationship("Simulation", back_populates="attempts")

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "simulation_id": self.simulation_id,
      "diagnosis_selected": self.diagnosis_selected,
      "treatment_selected": self.treatment_selected,
      "ai_feedback": self.ai_feedback,
      "score": self.score,
      "simulation": self.simulation.to_dict() if self.simulation else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
