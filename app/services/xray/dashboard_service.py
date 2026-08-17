"""X-ray dashboard aggregation (Module 10)."""

from __future__ import annotations

from collections import Counter

from app.models.xray_analysis_model import (
  XRAY_STATUS_ANALYZING,
  XRAY_STATUS_COMPLETED,
  XRAY_STATUS_FAILED,
  XRAY_STATUS_PREPROCESSING,
  XRAY_STATUS_UPLOADED,
  XrayAnalysis,
)


class XrayDashboardService:
  """Build owner-scoped X-ray dashboard widgets."""

  @classmethod
  def build_for_user(cls, user_id: int, *, recent_limit: int = 6) -> dict:
    rows = (
      XrayAnalysis.query.filter_by(user_id=user_id)
      .order_by(XrayAnalysis.created_at.desc())
      .all()
    )

    status_counts = Counter((r.status or XRAY_STATUS_UPLOADED).lower() for r in rows)
    completed = [r for r in rows if (r.status or "").lower() == XRAY_STATUS_COMPLETED]
    confidences = [float(r.confidence) for r in completed if r.confidence is not None]
    avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None

    body_parts = Counter((r.body_part or "Unknown") for r in rows)

    recent_xrays = [r.to_history_card() for r in rows[:recent_limit]]
    recent_analyses = [r.to_history_card() for r in completed[:recent_limit]]

    # Flatten unique learning recommendations from newest completed analyses
    learning_recommendations: list[dict] = []
    seen: set[str] = set()
    for row in completed[:12]:
      for item in row.learning_recommendations or []:
        if not isinstance(item, dict):
          continue
        title = str(item.get("title") or "").strip()
        href = str(item.get("href") or "")
        key = f"{item.get('type')}:{title}:{item.get('course_id')}"
        if not title or key in seen:
          continue
        seen.add(key)
        learning_recommendations.append(
          {
            "title": title,
            "type": item.get("type") or "topic",
            "reason": item.get("reason"),
            "href": href or (f"/learning/{item['course_id']}" if item.get("course_id") else "/learning"),
            "course_id": item.get("course_id"),
            "comparison_aware": bool(
              item.get("comparison_aware") or item.get("source") == "comparison"
            ),
            "source_xray_id": row.id,
            "source_filename": row.filename,
            "source_has_comparison": bool(
              getattr(row, "reference_image_path", None) or getattr(row, "comparison_summary", None)
            ),
          }
        )
        if len(learning_recommendations) >= 8:
          break
      if len(learning_recommendations) >= 8:
        break

    return {
      "stats": {
        "total_uploads": len(rows),
        "completed_analyses": status_counts.get(XRAY_STATUS_COMPLETED, 0),
        "failed_analyses": status_counts.get(XRAY_STATUS_FAILED, 0),
        "pending_or_processing": (
          status_counts.get(XRAY_STATUS_UPLOADED, 0)
          + status_counts.get(XRAY_STATUS_PREPROCESSING, 0)
          + status_counts.get(XRAY_STATUS_ANALYZING, 0)
        ),
        "with_heatmap": sum(1 for r in rows if r.heatmap_path),
        "average_confidence": avg_confidence,
        "by_status": dict(status_counts),
        "by_body_part": dict(body_parts),
      },
      "recent_xrays": recent_xrays,
      "recent_analyses": recent_analyses,
      "learning_recommendations": learning_recommendations,
    }
