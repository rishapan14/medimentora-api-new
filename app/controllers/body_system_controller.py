"""Student controllers for AI Human Body Systems Learning Hub (Phase 2)."""

from __future__ import annotations

from flask import request
from flask_jwt_extended import current_user

from app.helpers.response import error_response, success_response
from app.services.body_systems.hub_case_service import HubCaseService
from app.services.body_systems.hub_flashcard_service import HubFlashcardService
from app.services.body_systems.hub_quiz_service import HubQuizService
from app.services.body_systems.hub_service import BodySystemHubService
from app.services.body_systems.tutor_service import HubAiTutorService
from app.validations.body_system_validation import validate_progress_payload, validate_tutor_payload


def _page_args():
  try:
    page = int(request.args.get("page") or 1)
  except (TypeError, ValueError):
    page = 1
  try:
    per_page = int(request.args.get("per_page") or request.args.get("limit") or 20)
  except (TypeError, ValueError):
    per_page = 20
  return page, per_page


def list_body_systems():
  """GET /api/learning/body-systems"""
  page, per_page = _page_args()
  payload = BodySystemHubService.list_systems(
    user_id=getattr(current_user, "id", None),
    q=request.args.get("q") or request.args.get("search"),
    difficulty=request.args.get("difficulty"),
    page=page,
    per_page=per_page,
  )
  return success_response("Body systems retrieved.", payload)


def get_body_system(slug: str):
  """GET /api/learning/body-systems/<slug>"""
  payload = BodySystemHubService.get_system(slug, user_id=getattr(current_user, "id", None))
  if not payload:
    return error_response("Body system not found.", 404)
  return success_response("Body system retrieved.", payload)


def list_system_hub_quizzes(slug: str):
  """GET /api/learning/body-systems/<slug>/quizzes"""
  payload = HubQuizService.list_system_quizzes(slug, user_id=getattr(current_user, "id", None))
  if payload is None:
    return error_response("Body system not found.", 404)
  return success_response("Hub quizzes retrieved.", payload)


def generate_system_hub_quiz(slug: str):
  """POST /api/learning/body-systems/<slug>/quizzes/generate"""
  body = request.get_json(silent=True) or {}
  force = bool(body.get("force"))
  payload, code = HubQuizService.generate_system_quiz(
    slug,
    user_id=getattr(current_user, "id", None),
    difficulty=body.get("difficulty"),
    organ_slug=body.get("organ_slug") or body.get("organ"),
    force=force,
  )
  if code == "not_found":
    return error_response("Body system or organ not found.", 404)
  if code == "validation_error" or payload is None:
    return error_response("Could not generate quiz from available lesson content.", 400)
  return success_response(
    "Hub quiz ready." if not payload.get("generated") else "Hub quiz generated.",
    payload,
    201 if payload.get("generated") else 200,
  )


def list_system_hub_cases(slug: str):
  """GET /api/learning/body-systems/<slug>/cases"""
  payload = HubCaseService.list_system_cases(
    slug,
    organ_slug=request.args.get("organ"),
    disease_slug=request.args.get("disease"),
  )
  if payload is None:
    return error_response("Body system not found.", 404)
  return success_response("Hub clinical cases retrieved.", payload)


def generate_system_hub_cases(slug: str):
  """POST /api/learning/body-systems/<slug>/cases/generate"""
  body = request.get_json(silent=True) or {}
  payload, code = HubCaseService.generate_system_cases(
    slug,
    organ_slug=body.get("organ_slug") or body.get("organ"),
    force=bool(body.get("force")),
    user_id=getattr(current_user, "id", None),
  )
  if code == "not_found":
    return error_response("Body system or organ not found.", 404)
  if code == "validation_error" or payload is None:
    return error_response("Could not generate clinical cases from lesson content.", 400)
  return success_response(
    "Hub clinical cases ready." if not payload.get("generated") else "Hub clinical cases generated.",
    payload,
    201 if payload.get("generated") else 200,
  )


def list_system_organs(slug: str):
  """GET /api/learning/body-systems/<slug>/organs"""
  page, per_page = _page_args()
  payload = BodySystemHubService.list_organs(
    slug,
    q=request.args.get("q") or request.args.get("search"),
    page=page,
    per_page=per_page,
  )
  if payload is None:
    return error_response("Body system not found.", 404)
  return success_response("Organs retrieved.", payload)


def get_organ(slug: str):
  """GET /api/learning/organs/<slug>"""
  system_slug = request.args.get("system") or request.args.get("body_system")
  payload = BodySystemHubService.get_organ(
    slug,
    system_slug=system_slug,
    user_id=getattr(current_user, "id", None),
  )
  if not payload:
    return error_response("Organ not found.", 404)
  return success_response("Organ retrieved.", payload)


def get_hub_progress():
  """GET /api/learning/hub/progress — Phase 12 progress dashboard."""
  payload = BodySystemHubService.get_progress_summary(current_user.id)
  return success_response("Hub progress retrieved.", payload)


def list_hub_certificates():
  """GET /api/learning/hub/certificates — Phase 13 educational certificates."""
  from app.services.body_systems.hub_certificate_service import HubCertificateService

  try:
    limit = int(request.args.get("limit") or 50)
  except (TypeError, ValueError):
    limit = 50
  payload = HubCertificateService.list_for_user(current_user.id, limit=limit)
  return success_response("Hub certificates retrieved.", payload)


def get_hub_certificate(certificate_id: int):
  """GET /api/learning/hub/certificates/<id>"""
  from app.services.body_systems.hub_certificate_service import HubCertificateService

  payload = HubCertificateService.get_for_user(certificate_id, current_user.id)
  if not payload:
    return error_response("Certificate not found.", 404)
  return success_response("Hub certificate retrieved.", {"certificate": payload})


def download_hub_certificate(certificate_id: int):
  """GET /api/learning/hub/certificates/<id>/download"""
  import os

  from flask import send_file

  from app.services.body_systems.hub_certificate_service import HubCertificateService

  cert = HubCertificateService.get_row_for_user(certificate_id, current_user.id)
  if not cert:
    return error_response("Certificate not found.", 404)
  if not cert.file_path or not os.path.exists(cert.file_path):
    # Try regenerate PDF if missing
    try:
      from app.models.body_system_model import BodySystem
      from app.models.user_model import User

      user = User.query.get(current_user.id)
      system = BodySystem.query.get(cert.body_system_id)
      if user and system:
        cert.file_path = HubCertificateService.generate_certificate_pdf(
          user, system, cert.certificate_number
        )
        from app.extensions import db

        db.session.commit()
    except Exception:
      return error_response("Certificate file not found.", 404)
  if not cert.file_path or not os.path.exists(cert.file_path):
    return error_response("Certificate file not found.", 404)
  return send_file(
    cert.file_path,
    as_attachment=True,
    download_name=f"{cert.certificate_number}.pdf",
    mimetype="application/pdf",
  )


def list_system_diseases(slug: str):
  """GET /api/learning/body-systems/<slug>/diseases"""
  page, per_page = _page_args()
  payload = BodySystemHubService.list_diseases(
    slug,
    q=request.args.get("q") or request.args.get("search"),
    organ_slug=request.args.get("organ"),
    page=page,
    per_page=per_page,
  )
  if payload is None:
    return error_response("Body system not found.", 404)
  return success_response("Diseases retrieved.", payload)


def get_disease(slug: str):
  """GET /api/learning/diseases/<slug>"""
  system_slug = request.args.get("system") or request.args.get("body_system")
  payload = BodySystemHubService.get_disease(slug, system_slug=system_slug)
  if not payload:
    return error_response("Disease not found.", 404)
  return success_response("Disease retrieved.", payload)


def hub_search():
  """GET /api/learning/hub/search?q="""
  q = request.args.get("q") or request.args.get("search") or ""
  try:
    limit = int(request.args.get("limit") or 20)
  except (TypeError, ValueError):
    limit = 20
  payload = BodySystemHubService.search(q, limit=limit)
  return success_response("Hub search completed.", payload)


def list_hub_recommendations():
  """GET /api/learning/hub/recommendations"""
  try:
    limit = int(request.args.get("limit") or 20)
  except (TypeError, ValueError):
    limit = 20
  source_id = request.args.get("source_id")
  try:
    source_id_int = int(source_id) if source_id not in (None, "") else None
  except (TypeError, ValueError):
    source_id_int = None
  payload = BodySystemHubService.list_recommendations(
    current_user.id,
    limit=limit,
    source_type=request.args.get("source_type") or request.args.get("source"),
    source_id=source_id_int,
  )
  return success_response("Hub recommendations retrieved.", payload)


def list_hub_flashcards():
  """GET /api/learning/hub/flashcards"""
  page, per_page = _page_args()
  favorites_only = str(request.args.get("favorites") or "").lower() in ("1", "true", "yes")
  payload = HubFlashcardService.list_cards(
    user_id=getattr(current_user, "id", None),
    system_slug=request.args.get("system"),
    organ_slug=request.args.get("organ"),
    card_level=request.args.get("level") or request.args.get("card_level"),
    favorites_only=favorites_only,
    page=page,
    per_page=per_page,
  )
  return success_response("Flashcards retrieved.", payload)


def generate_hub_flashcards():
  """POST /api/learning/hub/flashcards/generate"""
  body = request.get_json(silent=True) or {}
  system_slug = (body.get("system_slug") or body.get("system") or "").strip()
  if not system_slug:
    return error_response("system_slug is required.", 400, {"error_code": "validation_error"})
  levels = body.get("levels")
  if isinstance(levels, str):
    levels = [levels]
  payload, code = HubFlashcardService.generate(
    system_slug=system_slug,
    organ_slug=body.get("organ_slug") or body.get("organ"),
    levels=levels,
    force=bool(body.get("force")),
    user_id=getattr(current_user, "id", None),
  )
  if code == "not_found":
    return error_response("Body system or organ not found.", 404)
  if code == "validation_error" or payload is None:
    return error_response("Could not generate flashcards from lesson content.", 400)
  return success_response(
    "Flashcards ready." if not payload.get("generated") else "Flashcards generated.",
    payload,
    201 if payload.get("generated") else 200,
  )


def list_hub_flashcard_favorites():
  """GET /api/learning/hub/flashcards/favorites"""
  page, per_page = _page_args()
  payload = HubFlashcardService.list_favorites(current_user.id, page=page, per_page=per_page)
  return success_response("Flashcard favorites retrieved.", payload)


def favorite_hub_flashcard(flashcard_id: int):
  """POST /api/learning/hub/flashcards/<id>/favorite"""
  payload, code = HubFlashcardService.add_favorite(current_user.id, flashcard_id)
  if code == "not_found":
    return error_response("Flashcard not found.", 404)
  return success_response("Flashcard favorited.", payload)


def unfavorite_hub_flashcard(flashcard_id: int):
  """DELETE /api/learning/hub/flashcards/<id>/favorite"""
  ok, code = HubFlashcardService.remove_favorite(current_user.id, flashcard_id)
  if code == "not_found" or not ok:
    return error_response("Favorite not found.", 404)
  return success_response("Flashcard unfavorited.")


def get_hub_explorer():
  """GET /api/learning/hub/explorer — Phase 5 interactive body catalog."""
  payload = BodySystemHubService.get_explorer_catalog()
  return success_response("Body explorer catalog retrieved.", payload)


def list_hub_tutor_modes():
  """GET /api/learning/hub/tutor/modes"""
  return success_response(
    "AI Tutor modes retrieved.",
    {
      "modes": HubAiTutorService.list_modes(),
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
      },
    },
  )


def hub_ai_tutor():
  """POST /api/learning/hub/tutor — Phase 6 context-grounded AI Tutor."""
  body = request.get_json(silent=True) or {}
  errors = validate_tutor_payload(body)
  if errors:
    return error_response(errors[0], 400, {"error_code": "validation_error"})

  payload, code = HubAiTutorService.tutor(
    mode=str(body.get("mode") or "explain_simply"),
    message=body.get("message"),
    organ_slug=(body.get("organ_slug") or body.get("organ") or None),
    system_slug=(body.get("system_slug") or body.get("system") or body.get("body_system") or None),
    language=body.get("language"),
    source=(body.get("source") or body.get("viewer") or None),
  )
  if code == "validation_error":
    return error_response("Invalid tutor request.", 400, {"error_code": "validation_error"})
  if code == "not_found" or payload is None:
    return error_response("Organ or body system not found.", 404)
  return success_response("AI Tutor response ready.", payload)


def start_body_system_progress(slug: str):
  """POST /api/learning/body-systems/<slug>/start"""
  payload = BodySystemHubService.get_or_start_progress(current_user.id, slug)
  if not payload:
    return error_response("Body system not found.", 404)
  return success_response("Learning progress started.", payload)


def get_body_system_progress(slug: str):
  """GET /api/learning/body-systems/<slug>/progress"""
  detail = BodySystemHubService.get_system(slug, user_id=current_user.id)
  if not detail:
    return error_response("Body system not found.", 404)
  return success_response(
    "Progress retrieved.",
    {
      "body_system": {
        "id": detail["id"],
        "slug": detail["slug"],
        "name": detail["name"],
      },
      "progress": detail["progress"],
      "can_continue": detail.get("can_continue"),
      "safety": detail.get("safety"),
    },
  )


def update_body_system_progress(slug: str):
  """PUT/PATCH /api/learning/body-systems/<slug>/progress"""
  body = request.get_json(silent=True) or {}
  errors = validate_progress_payload(body)
  if errors:
    return error_response(errors[0], 400, {"error_code": "validation_error"})
  payload, code = BodySystemHubService.update_progress(current_user.id, slug, body)
  if code == "not_found" or payload is None:
    return error_response("Body system not found.", 404)
  if code == "validation_error":
    return error_response("Invalid progress payload.", 400, {"error_code": "validation_error"})
  return success_response("Progress updated.", payload)
