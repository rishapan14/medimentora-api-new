from flask import request
from flask_jwt_extended import current_user

from app.extensions import db
from app.helpers.response import error_response, success_response
from app.models.report_analysis_model import ReportAnalysis
from app.models.report_model import Report
from app.services.ai_analysis_service import AIAnalysisService
from app.utils import utc_now
from app.validations.analysis_validation import validate_analysis


def _confidence_label(analysis_data: dict) -> str:
  """Derive a High/Medium/Low label from analysis payload."""
  abnormal = analysis_data.get("abnormal_values") or []
  parsed = analysis_data.get("parsed_tests") or []
  mode = analysis_data.get("analysis_mode")
  if mode == "openai" and (abnormal or parsed):
    return "High"
  if abnormal or parsed or analysis_data.get("simple_explanation"):
    return "Medium"
  return "Low"


def analyze_report():
  from app.services.admin.settings_admin_service import AdminSettingsService

  blocked = AdminSettingsService.deny_if_maintenance()
  if blocked:
    return blocked
  blocked = AdminSettingsService.deny_if_feature_disabled(
    "ai_report_analysis_enabled",
    message="AI Report Analysis is currently disabled by the administrator.",
  )
  if blocked:
    return blocked

  data = request.get_json(silent=True)
  errors = validate_analysis(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  report_text = data.get("report_text")
  report_id = data.get("report_id")
  report = None

  if report_id:
    report = Report.query.filter_by(id=report_id, user_id=current_user.id).first()
    if not report:
      return error_response("Report not found.", 404)
    report_text = (report.extracted_text or report_text or "").strip()
    if not report_text:
      return error_response("No text available for analysis. Extract text first.", 400)
  else:
    report_text = (report_text or "").strip()
    if not report_text:
      return error_response("report_text is required.", 400)

  try:
    analysis_data = AIAnalysisService.analyze_report(report_text)
  except ValueError as exc:
    return error_response(str(exc), 422)
  except Exception as exc:
    return error_response(f"AI analysis failed: {exc}", 500)

  record = ReportAnalysis(
    user_id=current_user.id,
    report_id=report_id,
    report_text=report_text,
    simple_explanation=analysis_data.get("simple_explanation"),
    abnormal_values=analysis_data.get("abnormal_values"),
    possible_diseases=analysis_data.get("possible_diseases"),
    medical_terms=analysis_data.get("medical_terms"),
    learning_topics=analysis_data.get("learning_topics"),
    full_response=analysis_data,
  )
  db.session.add(record)

  # Persist history metadata on the parent report so list views stay fast
  if report is not None:
    now = utc_now()
    report.status = "analyzed"
    report.analysis_date = now
    report.updated_at = now
    report.analysis_confidence = _confidence_label(analysis_data)
    report.report_type = analysis_data.get("report_type") or report.report_type or "general"
    report.structured_json = {
      "abnormal_values": analysis_data.get("abnormal_values") or [],
      "normal_values": analysis_data.get("normal_values") or [],
      "parsed_tests": analysis_data.get("parsed_tests") or [],
      "possible_diseases": analysis_data.get("possible_diseases") or [],
      "medical_terms": analysis_data.get("medical_terms") or [],
      "learning_topics": analysis_data.get("learning_topics") or [],
      "simple_explanation": analysis_data.get("simple_explanation"),
      "analysis_mode": analysis_data.get("analysis_mode"),
      "report_type": analysis_data.get("report_type"),
    }

  db.session.commit()

  hub_recommendations: list = []
  try:
    from app.services.body_systems.hub_report_recommendation_service import (
      HubReportRecommendationService,
    )

    hub_recommendations = HubReportRecommendationService.recommend_for_analysis(
      record, user_id=current_user.id
    )
  except Exception:
    hub_recommendations = []

  payload = record.to_dict()
  payload["hub_recommendations"] = hub_recommendations
  payload["safety"] = {
    "educational_only": True,
    "not_a_diagnosis": True,
    "note": "Report analysis and hub recommendations are for educational learning only.",
  }
  return success_response("Analysis completed.", {"analysis": payload}, 201)


def get_analysis(analysis_id):
  record = ReportAnalysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
  if not record:
    return error_response("Analysis not found.", 404)
  return success_response("Analysis retrieved.", {"analysis": record.to_dict()})


def list_analyses():
  records = ReportAnalysis.query.filter_by(user_id=current_user.id).order_by(
    ReportAnalysis.created_at.desc()
  ).all()
  return success_response("Analysis history retrieved.", {
    "analyses": [r.to_dict() for r in records],
    "total": len(records),
  })


def delete_analysis(analysis_id):
  record = ReportAnalysis.query.filter_by(id=analysis_id, user_id=current_user.id).first()
  if not record:
    return error_response("Analysis not found.", 404)
  db.session.delete(record)
  db.session.commit()
  return success_response("Analysis deleted.")
