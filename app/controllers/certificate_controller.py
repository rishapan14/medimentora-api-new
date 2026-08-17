import os

from flask import current_app, request, send_file
from flask_jwt_extended import current_user

from app.extensions import db
from app.helpers.response import error_response, success_response
from app.models.certificate_model import Certificate
from app.models.course_model import Course
from app.services.certificate_service import CertificateService
from app.services.notification_service import NotificationService
from app.validations.certificate_validation import validate_certificate


def generate_certificate():
  data = request.get_json(silent=True)
  errors = validate_certificate(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  course = Course.query.get(data["course_id"])
  if not course:
    return error_response("Course not found.", 404)

  existing = Certificate.query.filter_by(user_id=current_user.id, course_id=course.id).first()
  if existing:
    return success_response("Certificate already exists.", {"certificate": existing.to_dict()})

  cert_number = CertificateService.generate_certificate_number()
  file_path = CertificateService.generate_certificate_pdf(current_user, course, cert_number)

  cert = Certificate(
    user_id=current_user.id,
    course_id=course.id,
    certificate_number=cert_number,
    file_path=file_path,
  )
  db.session.add(cert)
  db.session.commit()

  NotificationService.certificate_issued(current_user.id, course.title, cert.id)

  return success_response("Certificate generated.", {"certificate": cert.to_dict()}, 201)


def list_certificates():
  certs = Certificate.query.filter_by(user_id=current_user.id).order_by(Certificate.issued_at.desc()).all()
  return success_response("Certificates retrieved.", {"certificates": [c.to_dict() for c in certs]})


def download_certificate(certificate_id):
  cert = Certificate.query.filter_by(id=certificate_id, user_id=current_user.id).first()
  if not cert:
    return error_response("Certificate not found.", 404)
  if not cert.file_path or not os.path.exists(cert.file_path):
    return error_response("Certificate file not found.", 404)

  return send_file(
    cert.file_path,
    as_attachment=True,
    download_name=f"{cert.certificate_number}.pdf",
    mimetype="application/pdf",
  )


def get_certificate(certificate_id):
  cert = Certificate.query.filter_by(id=certificate_id, user_id=current_user.id).first()
  if not cert:
    return error_response("Certificate not found.", 404)
  return success_response("Certificate retrieved.", {"certificate": cert.to_dict()})
