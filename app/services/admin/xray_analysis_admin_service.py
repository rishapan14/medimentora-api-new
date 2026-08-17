"""Admin monitoring for AI X-Ray Analysis (Module 6 / Phase 16)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func

from app.extensions import db
from app.models.user_model import User
from app.models.xray_analysis_model import XrayAnalysis
from app.services.xray.upload_service import XrayUploadService

logger = logging.getLogger(__name__)


class AdminXrayAnalysisService:
  """Platform-wide list / detail / delete for X-ray analyses."""

  @classmethod
  def _admin_row(cls, row: XrayAnalysis) -> dict[str, Any]:
    user = row.user
    findings = row.possible_findings if isinstance(row.possible_findings, list) else []
    structured = row.structured_findings if isinstance(row.structured_findings, dict) else {}
    structured_findings = structured.get("findings") if isinstance(structured.get("findings"), list) else []
    if not findings and structured_findings:
      findings = structured_findings

    top_finding = None
    if findings:
      first = findings[0]
      if isinstance(first, dict):
        top_finding = first.get("label") or first.get("finding") or first.get("name")
      else:
        top_finding = str(first)

    extras = row.clinical_extras if isinstance(row.clinical_extras, dict) else {}
    projection = extras.get("projection")
    quality = row.image_quality if isinstance(row.image_quality, dict) else {}
    body_det = row.body_detection if isinstance(row.body_detection, dict) else {}
    proj_det = row.projection_detection if isinstance(row.projection_detection, dict) else {}
    heatmap_meta = row.heatmap_meta if isinstance(getattr(row, "heatmap_meta", None), dict) else {}

    summary = (row.ai_summary or "").strip()
    return {
      "id": row.id,
      "user_id": row.user_id,
      "user_email": getattr(user, "email", None),
      "user_name": getattr(user, "full_name", None),
      "filename": row.filename,
      "body_part": row.body_part,
      "projection": projection,
      "status": row.status,
      "confidence": row.confidence,
      "model_name": row.model_name,
      "top_finding": top_finding,
      "findings_count": len(findings),
      "has_comparison": bool(row.reference_image_path or row.comparison_summary),
      "has_heatmap": bool(row.heatmap_path),
      "has_structured_findings": bool(structured_findings),
      "heatmap_method": heatmap_meta.get("method"),
      "image_quality_score": quality.get("quality_score"),
      "image_quality_grade": quality.get("grade"),
      "image_quality_is_poor": bool(quality.get("is_poor")) if quality else None,
      "detected_body_part": body_det.get("body_part"),
      "detected_projection": proj_det.get("projection"),
      "ai_summary_preview": (summary[:160] + "…") if len(summary) > 160 else summary,
      "patient_age": row.patient_age,
      "gender": row.gender,
      "smoking_history": row.smoking_history,
      "analysis_version": row.analysis_version,
      "specialist_key": (
        (row.model_routing or {}).get("specialist_key")
        if isinstance(row.model_routing, dict)
        else None
      ),
      "error_message": row.error_message,
      "upload_date": row.upload_date.isoformat() if row.upload_date else None,
      "analysis_date": row.analysis_date.isoformat() if row.analysis_date else None,
      "created_at": row.created_at.isoformat() if row.created_at else None,
    }

  @classmethod
  def _admin_detail(cls, row: XrayAnalysis) -> dict[str, Any]:
    payload = row.to_dict(include_explanation=True)
    user = row.user
    payload["user_email"] = getattr(user, "email", None)
    payload["user_name"] = getattr(user, "full_name", None)
    # Phase 16 convenience flags for the admin UI
    payload["has_heatmap"] = bool(row.heatmap_path)
    payload["has_comparison"] = bool(row.reference_image_path or row.comparison_summary)
    return payload

  @classmethod
  def list_analyses(
    cls,
    *,
    q: str | None = None,
    body_part: str | None = None,
    status: str | None = None,
    user_id: int | None = None,
    has_heatmap: bool | None = None,
    has_comparison: bool | None = None,
    limit: int = 50,
    offset: int = 0,
  ) -> dict[str, Any]:
    query = XrayAnalysis.query.outerjoin(User, XrayAnalysis.user_id == User.id)

    if user_id is not None:
      query = query.filter(XrayAnalysis.user_id == int(user_id))

    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        db.or_(
          User.email.ilike(like),
          User.full_name.ilike(like),
          XrayAnalysis.filename.ilike(like),
          XrayAnalysis.ai_summary.ilike(like),
          XrayAnalysis.body_part.ilike(like),
        )
      )

    part = (body_part or "").strip()
    if part and part.lower() not in ("all", ""):
      query = query.filter(XrayAnalysis.body_part.ilike(part))

    st = (status or "").strip().lower()
    if st and st not in ("all", ""):
      query = query.filter(XrayAnalysis.status == st)

    if has_heatmap is True:
      query = query.filter(XrayAnalysis.heatmap_path.isnot(None))
    elif has_heatmap is False:
      query = query.filter(XrayAnalysis.heatmap_path.is_(None))

    if has_comparison is True:
      query = query.filter(
        db.or_(
          XrayAnalysis.reference_image_path.isnot(None),
          XrayAnalysis.comparison_summary.isnot(None),
        )
      )
    elif has_comparison is False:
      query = query.filter(
        XrayAnalysis.reference_image_path.is_(None),
        XrayAnalysis.comparison_summary.is_(None),
      )

    total = query.count()
    rows = (
      query.order_by(XrayAnalysis.created_at.desc(), XrayAnalysis.id.desc())
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
      "filters_applied": {
        "q": q or None,
        "body_part": body_part or None,
        "status": status or None,
        "user_id": user_id,
        "has_heatmap": has_heatmap,
        "has_comparison": has_comparison,
      },
    }

  @classmethod
  def stats(cls) -> dict[str, Any]:
    total = XrayAnalysis.query.count()
    users_with = (
      db.session.query(func.count(func.distinct(XrayAnalysis.user_id))).scalar() or 0
    )
    with_comparison = XrayAnalysis.query.filter(
      db.or_(
        XrayAnalysis.reference_image_path.isnot(None),
        XrayAnalysis.comparison_summary.isnot(None),
      )
    ).count()
    with_heatmap = XrayAnalysis.query.filter(
      XrayAnalysis.heatmap_path.isnot(None)
    ).count()

    by_status: dict[str, int] = {}
    for status, count in (
      db.session.query(XrayAnalysis.status, func.count(XrayAnalysis.id))
      .group_by(XrayAnalysis.status)
      .all()
    ):
      by_status[str(status or "unknown")] = int(count)

    by_body_part: dict[str, int] = {}
    for part, count in (
      db.session.query(XrayAnalysis.body_part, func.count(XrayAnalysis.id))
      .group_by(XrayAnalysis.body_part)
      .all()
    ):
      by_body_part[str(part or "unspecified")] = int(count)

    return {
      "total": total,
      "unique_users": int(users_with),
      "with_comparison": int(with_comparison),
      "with_heatmap": int(with_heatmap),
      "completed": by_status.get("completed", 0),
      "failed": by_status.get("failed", 0),
      "by_status": by_status,
      "by_body_part": by_body_part,
    }

  @classmethod
  def get_analysis(cls, xray_id: int) -> XrayAnalysis | None:
    return db.session.get(XrayAnalysis, xray_id)

  @classmethod
  def get_analysis_payload(cls, xray_id: int) -> dict[str, Any] | None:
    row = cls.get_analysis(xray_id)
    if not row:
      return None
    return cls._admin_detail(row)

  @classmethod
  def delete_analysis(cls, xray_id: int) -> dict[str, Any]:
    row = cls.get_analysis(xray_id)
    if not row:
      return {"success": False, "message": "X-ray analysis not found.", "error_code": "not_found"}
    try:
      XrayUploadService.delete_row(row)
      return {"success": True, "message": "X-ray analysis deleted."}
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin delete xray analysis failed id=%s", xray_id)
      return {
        "success": False,
        "message": "Could not delete X-ray analysis.",
        "error_code": "delete_failed",
        "data": {"detail": str(exc)},
      }
