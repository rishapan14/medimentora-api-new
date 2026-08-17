from flask import request
from flask_jwt_extended import current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.helpers.response import error_response, success_response
from app.models.clinical_case_model import CaseFavorite, ClinicalCase
from app.validations.clinical_case_validation import validate_clinical_case


def list_cases():
  query = ClinicalCase.query.filter_by(is_published=True)
  disease = request.args.get("disease")
  speciality = request.args.get("speciality")
  difficulty = request.args.get("difficulty")
  search = request.args.get("search")

  if disease:
    query = query.filter(ClinicalCase.disease.ilike(f"%{disease}%"))
  if speciality:
    query = query.filter(ClinicalCase.speciality.ilike(f"%{speciality}%"))
  if difficulty:
    query = query.filter_by(difficulty=difficulty)
  if search:
    query = query.filter(
      or_(
        ClinicalCase.title.ilike(f"%{search}%"),
        ClinicalCase.disease.ilike(f"%{search}%"),
        ClinicalCase.description.ilike(f"%{search}%"),
      )
    )

  cases = query.order_by(ClinicalCase.created_at.desc()).all()
  favorited_ids = {
    fav.case_id
    for fav in CaseFavorite.query.filter_by(user_id=current_user.id).all()
  }
  return success_response("Clinical cases retrieved.", {
    "cases": [{**c.to_dict(), "bookmarked": c.id in favorited_ids} for c in cases],
  })


def get_case(case_id):
  case = ClinicalCase.query.get(case_id)
  if not case:
    return error_response("Clinical case not found.", 404)
  bookmarked = CaseFavorite.query.filter_by(
    user_id=current_user.id, case_id=case_id
  ).first() is not None
  return success_response("Clinical case retrieved.", {
    "case": {**case.to_dict(), "bookmarked": bookmarked},
  })


def create_case():
  data = request.get_json(silent=True)
  errors = validate_clinical_case(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  case = ClinicalCase(
    created_by=current_user.id,
    title=data["title"],
    disease=data["disease"],
    symptoms=data.get("symptoms", []),
    diagnosis=data.get("diagnosis"),
    treatment=data.get("treatment"),
    difficulty=data.get("difficulty", "medium"),
    speciality=data.get("speciality"),
    description=data.get("description"),
    is_published=data.get("is_published", True),
  )
  db.session.add(case)
  db.session.commit()
  return success_response("Clinical case created.", {"case": case.to_dict()}, 201)


def update_case(case_id):
  case = ClinicalCase.query.get(case_id)
  if not case:
    return error_response("Clinical case not found.", 404)

  data = request.get_json(silent=True) or {}
  errors = validate_clinical_case(data, partial=True)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  for field in (
    "title", "disease", "symptoms", "diagnosis", "treatment",
    "difficulty", "speciality", "description", "is_published",
  ):
    if field in data:
      setattr(case, field, data[field])
  db.session.commit()
  return success_response("Clinical case updated.", {"case": case.to_dict()})


def delete_case(case_id):
  case = ClinicalCase.query.get(case_id)
  if not case:
    return error_response("Clinical case not found.", 404)
  db.session.delete(case)
  db.session.commit()
  return success_response("Clinical case deleted.")


def favorite_case(case_id):
  case = ClinicalCase.query.get(case_id)
  if not case:
    return error_response("Clinical case not found.", 404)

  existing = CaseFavorite.query.filter_by(user_id=current_user.id, case_id=case_id).first()
  if existing:
    return success_response("Already favorited.", {"favorite": existing.to_dict()})

  fav = CaseFavorite(user_id=current_user.id, case_id=case_id)
  db.session.add(fav)
  try:
    db.session.commit()
  except IntegrityError:
    db.session.rollback()
    existing = CaseFavorite.query.filter_by(user_id=current_user.id, case_id=case_id).first()
    return success_response("Already favorited.", {"favorite": existing.to_dict() if existing else None})
  return success_response("Case favorited.", {"favorite": fav.to_dict()}, 201)


def unfavorite_case(case_id):
  fav = CaseFavorite.query.filter_by(user_id=current_user.id, case_id=case_id).first()
  if not fav:
    return error_response("Favorite not found.", 404)
  db.session.delete(fav)
  db.session.commit()
  return success_response("Favorite removed.")


def list_favorites():
  favs = CaseFavorite.query.filter_by(user_id=current_user.id).all()
  return success_response("Favorites retrieved.", {"favorites": [f.to_dict() for f in favs]})
