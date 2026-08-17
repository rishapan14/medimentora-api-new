"""Admin monitoring for AI Report Analysis (Module 5)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func

from app.extensions import db
from app.models.report_analysis_model import ReportAnalysis
from app.models.user_model import User

logger = logging.getLogger(__name__)


def _json_text(column, key: str):
  """MySQL-friendly JSON scalar as text (lowercased)."""
  return func.lower(func.json_unquote(func.json_extract(column, f"$.{key}")))


class AdminReportAnalysisService:
  """Platform-wide list / detail / delete for report analyses."""

  @classmethod
  def _admin_row(cls, row: ReportAnalysis) -> dict[str, Any]:
    full = row.full_response if isinstance(row.full_response, dict) else {}
    user = row.user
    abnormal = row.abnormal_values if isinstance(row.abnormal_values, list) else []
    diseases = row.possible_diseases if isinstance(row.possible_diseases, list) else []
    topics = row.learning_topics if isinstance(row.learning_topics, list) else []
    explanation = (row.simple_explanation or "").strip()
    return {
      "id": row.id,
      "user_id": row.user_id,
      "user_email": getattr(user, "email", None),
      "user_name": getattr(user, "full_name", None),
      "report_id": row.report_id,
      "report_type": full.get("report_type") or "general",
      "analysis_mode": full.get("analysis_mode"),
      "simple_explanation_preview": (
        (explanation[:160] + "…") if len(explanation) > 160 else explanation
      ),
      "abnormal_count": len(abnormal),
      "possible_disease_count": len(diseases),
      "learning_topic_count": len(topics),
      "created_at": row.created_at.isoformat() if row.created_at else None,
    }

  @classmethod
  def _admin_detail(cls, row: ReportAnalysis) -> dict[str, Any]:
    payload = row.to_dict()
    user = row.user
    payload["user_email"] = getattr(user, "email", None)
    payload["user_name"] = getattr(user, "full_name", None)
    return payload

  @classmethod
  def list_analyses(
    cls,
    *,
    q: str | None = None,
    report_type: str | None = None,
    analysis_mode: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
  ) -> dict[str, Any]:
    query = ReportAnalysis.query.outerjoin(User, ReportAnalysis.user_id == User.id)

    if user_id is not None:
      query = query.filter(ReportAnalysis.user_id == int(user_id))

    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        db.or_(
          User.email.ilike(like),
          User.full_name.ilike(like),
          ReportAnalysis.simple_explanation.ilike(like),
          ReportAnalysis.report_text.ilike(like),
        )
      )

    rtype = (report_type or "").strip().lower()
    if rtype and rtype not in ("all", ""):
      query = query.filter(_json_text(ReportAnalysis.full_response, "report_type") == rtype)

    mode = (analysis_mode or "").strip().lower()
    if mode and mode not in ("all", ""):
      query = query.filter(_json_text(ReportAnalysis.full_response, "analysis_mode") == mode)

    total = query.count()
    rows = (
      query.order_by(ReportAnalysis.created_at.desc(), ReportAnalysis.id.desc())
      .offset(max(0, offset))
      .limit(min(max(int(limit), 1), 200))
      .all()
    )

    return {
      "analyses": [cls._admin_row(r) for r in rows],
      "total": total,
      "offset": offset,
      "limit": limit,
      "stats": cls.stats(),
    }

  @classmethod
  def stats(cls) -> dict[str, Any]:
    total = ReportAnalysis.query.count()
    users_with = (
      db.session.query(func.count(func.distinct(ReportAnalysis.user_id))).scalar() or 0
    )

    abnormal_flagged = 0
    modes: dict[str, int] = {}
    types: dict[str, int] = {}
    for row in ReportAnalysis.query.with_entities(
      ReportAnalysis.abnormal_values,
      ReportAnalysis.full_response,
    ).all():
      vals, full = row[0], row[1]
      if isinstance(vals, list) and len(vals) > 0:
        abnormal_flagged += 1
      payload = full if isinstance(full, dict) else {}
      m = str(payload.get("analysis_mode") or "unknown")
      t = str(payload.get("report_type") or "general")
      modes[m] = modes.get(m, 0) + 1
      types[t] = types.get(t, 0) + 1

    return {
      "total": total,
      "unique_users": int(users_with),
      "with_abnormal_values": abnormal_flagged,
      "by_mode": modes,
      "by_report_type": types,
    }

  @classmethod
  def get_analysis(cls, analysis_id: int) -> ReportAnalysis | None:
    return db.session.get(ReportAnalysis, analysis_id)

  @classmethod
  def get_analysis_payload(cls, analysis_id: int) -> dict[str, Any] | None:
    row = cls.get_analysis(analysis_id)
    if not row:
      return None
    return cls._admin_detail(row)

  @classmethod
  def delete_analysis(cls, analysis_id: int) -> dict[str, Any]:
    row = cls.get_analysis(analysis_id)
    if not row:
      return {"success": False, "message": "Analysis not found.", "error_code": "not_found"}
    try:
      db.session.delete(row)
      db.session.commit()
      logger.info("Admin deleted report analysis id=%s", analysis_id)
      return {"success": True, "message": "Analysis deleted."}
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin delete analysis failed id=%s", analysis_id)
      return {
        "success": False,
        "message": "Could not delete analysis.",
        "error_code": "delete_failed",
        "data": {"detail": str(exc)},
      }
