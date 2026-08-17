"""Admin platform Reports / usage summaries (Module 10)."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

from sqlalchemy import func

from app.constants import ROLE_ADMIN
from app.extensions import db
from app.models.course_model import CompletedLesson, Course, Lesson
from app.models.quiz_model import Question, Quiz, Result
from app.models.reference_xray_library_model import ReferenceXrayLibrary
from app.models.report_analysis_model import ReportAnalysis
from app.models.simulation_model import Simulation, SimulationAttempt
from app.models.user_model import User
from app.models.xray_analysis_model import XrayAnalysis
from app.utils import utc_now


class AdminReportsService:
  """Platform-wide usage aggregates and CSV exports for Admin Panel."""

  @classmethod
  def overview(cls) -> dict[str, Any]:
    now = utc_now()
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    total_users = User.query.count()
    admin_users = User.query.filter(User.role == ROLE_ADMIN).count()
    active_users = User.query.filter_by(is_active=True).count()
    new_users_7d = User.query.filter(User.created_at >= since_7d).count()
    new_users_30d = User.query.filter(User.created_at >= since_30d).count()

    report_analyses = ReportAnalysis.query.count()
    report_analyses_7d = ReportAnalysis.query.filter(ReportAnalysis.created_at >= since_7d).count()

    xray_total = XrayAnalysis.query.count()
    xray_completed = XrayAnalysis.query.filter_by(status="completed").count()
    xray_7d = XrayAnalysis.query.filter(XrayAnalysis.created_at >= since_7d).count()

    references = ReferenceXrayLibrary.query.count()

    courses = Course.query.count()
    lessons = Lesson.query.count()
    lesson_completions = CompletedLesson.query.count()

    quizzes = Quiz.query.count()
    questions = Question.query.count()
    quiz_attempts = Result.query.count()
    quiz_attempts_7d = Result.query.filter(Result.completed_at >= since_7d).count()
    avg_quiz = db.session.query(func.avg(Result.score)).scalar()
    avg_quiz_score = round(float(avg_quiz), 2) if avg_quiz is not None else 0.0

    simulations = Simulation.query.count()
    sim_attempts = SimulationAttempt.query.count()
    sim_attempts_7d = SimulationAttempt.query.filter(
      SimulationAttempt.created_at >= since_7d
    ).count()
    avg_sim = db.session.query(func.avg(SimulationAttempt.score)).scalar()
    avg_sim_score = round(float(avg_sim), 2) if avg_sim is not None else 0.0

    recent_activity = cls._recent_activity(limit=12)

    return {
      "generated_at": now.isoformat(),
      "users": {
        "total": total_users,
        "admins": admin_users,
        "panel_users": max(0, total_users - admin_users),
        "active": active_users,
        "inactive": max(0, total_users - active_users),
        "new_7d": new_users_7d,
        "new_30d": new_users_30d,
      },
      "ai": {
        "report_analyses": report_analyses,
        "report_analyses_7d": report_analyses_7d,
        "xray_analyses": xray_total,
        "xray_completed": xray_completed,
        "xray_analyses_7d": xray_7d,
        "reference_images": references,
      },
      "learning": {
        "courses": courses,
        "lessons": lessons,
        "lesson_completions": lesson_completions,
      },
      "assessments": {
        "quizzes": quizzes,
        "questions": questions,
        "quiz_attempts": quiz_attempts,
        "quiz_attempts_7d": quiz_attempts_7d,
        "average_quiz_score": avg_quiz_score,
        "simulations": simulations,
        "simulation_attempts": sim_attempts,
        "simulation_attempts_7d": sim_attempts_7d,
        "average_simulation_score": avg_sim_score,
      },
      "recent_activity": recent_activity,
    }

  @classmethod
  def _recent_activity(cls, *, limit: int = 12) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for row in (
      ReportAnalysis.query.order_by(ReportAnalysis.created_at.desc()).limit(limit).all()
    ):
      items.append(
        {
          "type": "report_analysis",
          "id": row.id,
          "label": f"Report analysis #{row.id}",
          "user_id": row.user_id,
          "user_email": getattr(row.user, "email", None),
          "at": row.created_at.isoformat() if row.created_at else None,
        }
      )

    for row in XrayAnalysis.query.order_by(XrayAnalysis.created_at.desc()).limit(limit).all():
      items.append(
        {
          "type": "xray_analysis",
          "id": row.id,
          "label": row.filename or f"X-ray #{row.id}",
          "user_id": row.user_id,
          "user_email": getattr(row.user, "email", None),
          "at": row.created_at.isoformat() if row.created_at else None,
        }
      )

    for row in Result.query.order_by(Result.completed_at.desc()).limit(limit).all():
      quiz_title = row.quiz.title if row.quiz else f"Quiz #{row.quiz_id}"
      items.append(
        {
          "type": "quiz_attempt",
          "id": row.id,
          "label": f"{quiz_title} · {row.score}%",
          "user_id": row.user_id,
          "user_email": getattr(row.user, "email", None),
          "at": row.completed_at.isoformat() if row.completed_at else None,
        }
      )

    for row in (
      SimulationAttempt.query.order_by(SimulationAttempt.created_at.desc()).limit(limit).all()
    ):
      title = row.simulation.title if row.simulation else f"Simulation #{row.simulation_id}"
      items.append(
        {
          "type": "simulation_attempt",
          "id": row.id,
          "label": f"{title} · score {row.score}",
          "user_id": row.user_id,
          "user_email": getattr(row.user, "email", None),
          "at": row.created_at.isoformat() if row.created_at else None,
        }
      )

    items.sort(key=lambda x: x.get("at") or "", reverse=True)
    return items[:limit]

  @classmethod
  def export_users_csv(cls) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
      [
        "id",
        "email",
        "full_name",
        "role",
        "panel_role",
        "is_active",
        "speciality",
        "created_at",
      ]
    )
    for user in User.query.order_by(User.id.asc()).all():
      writer.writerow(
        [
          user.id,
          user.email,
          user.full_name or "",
          user.role,
          "Admin" if user.role == ROLE_ADMIN else "User",
          "true" if user.is_active else "false",
          user.speciality or "",
          user.created_at.isoformat() if user.created_at else "",
        ]
      )
    return output.getvalue()

  @classmethod
  def export_overview_csv(cls) -> str:
    data = cls.overview()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "metric", "value"])
    writer.writerow(["meta", "generated_at", data["generated_at"]])

    for section in ("users", "ai", "learning", "assessments"):
      for key, value in (data.get(section) or {}).items():
        writer.writerow([section, key, value])
    return output.getvalue()
