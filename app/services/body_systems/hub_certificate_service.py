"""Body Systems Hub educational certificates (Phase 13).

Auto-issued when a learner completes a body system pathway.
Educational completion only — never a professional license or diagnosis.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from flask import current_app, has_app_context

from app.extensions import db
from app.models.body_system_model import BodySystem, BodySystemProgress, HubCertificate
from app.models.user_model import User
from app.utils import utc_now

logger = logging.getLogger(__name__)

HUB_CERT_VERSION = "phase12-3d-v1"
EDUCATIONAL_DISCLAIMER = (
  "Educational completion only. This is not a professional license, "
  "clinical credential, or medical diagnosis."
)


class HubCertificateService:
  """Issue and list hub body-system certificates."""

  @classmethod
  def maybe_issue_for_progress(cls, progress: BodySystemProgress) -> dict[str, Any] | None:
    """Issue a certificate when progress is completed (idempotent)."""
    if not progress:
      return None
    pct = float(progress.progress_percent or 0)
    status = (progress.status or "").lower()
    if status != "completed" and pct < 100:
      return None

    existing = HubCertificate.query.filter_by(
      user_id=progress.user_id, body_system_id=progress.body_system_id
    ).first()
    if existing:
      return existing.to_dict()

    system = BodySystem.query.get(progress.body_system_id)
    if not system:
      return None
    user = User.query.get(progress.user_id)
    if not user:
      return None

    if status != "completed":
      progress.status = "completed"
      progress.progress_percent = max(pct, 100.0)
      progress.completed_at = progress.completed_at or utc_now()

    cert_number = cls.generate_certificate_number()
    title = f"Educational Completion — {system.name}"
    file_path = None
    try:
      file_path = cls.generate_certificate_pdf(user, system, cert_number)
    except Exception:
      logger.exception("Hub certificate PDF failed for user=%s system=%s", user.id, system.id)

    cert = HubCertificate(
      user_id=user.id,
      body_system_id=system.id,
      certificate_number=cert_number,
      title=title,
      file_path=file_path,
      progress_percent=float(progress.progress_percent or 100),
      study_minutes=int(progress.study_minutes or 0),
      issued_at=utc_now(),
      meta_json={
        "version": HUB_CERT_VERSION,
        "system_slug": system.slug,
        "system_name": system.name,
        "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
        "links": {
          "pathway": f"/learning/body-systems/{system.slug}",
          "explorer_3d": (
            f"/learning/body-systems/explorer-3d?mode={system.slug}&from=certificate"
          ),
        },
        "safety": {
          "educational_only": True,
          "not_a_license": True,
          "not_a_diagnosis": True,
        },
      },
    )
    db.session.add(cert)
    db.session.commit()

    try:
      from app.services.notification_service import NotificationService

      NotificationService.certificate_issued(user.id, title, cert.id)
    except Exception:
      logger.exception("Hub certificate notification failed id=%s", cert.id)

    return cert.to_dict()

  @classmethod
  def list_for_user(cls, user_id: int, *, limit: int = 50) -> dict[str, Any]:
    limit = min(100, max(1, int(limit or 50)))
    rows = (
      HubCertificate.query.filter_by(user_id=user_id)
      .order_by(HubCertificate.issued_at.desc())
      .limit(limit)
      .all()
    )
    return {
      "items": [r.to_dict() for r in rows],
      "total": len(rows),
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "not_a_license": True,
        "note": EDUCATIONAL_DISCLAIMER,
      },
    }

  @classmethod
  def get_for_user(cls, certificate_id: int, user_id: int) -> dict[str, Any] | None:
    row = HubCertificate.query.filter_by(id=certificate_id, user_id=user_id).first()
    return row.to_dict() if row else None

  @classmethod
  def get_row_for_user(cls, certificate_id: int, user_id: int) -> HubCertificate | None:
    return HubCertificate.query.filter_by(id=certificate_id, user_id=user_id).first()

  @staticmethod
  def generate_certificate_number() -> str:
    return f"HUB-{uuid.uuid4().hex[:12].upper()}"

  @classmethod
  def generate_certificate_pdf(cls, user: User, system: BodySystem, certificate_number: str) -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    if has_app_context():
      folder = current_app.config.get("CERTIFICATE_UPLOAD_FOLDER") or "uploads/certificates"
    else:
      folder = "uploads/certificates"
    os.makedirs(folder, exist_ok=True)

    filename = f"hub_cert_{certificate_number}.pdf"
    file_path = os.path.join(folder, filename)

    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 1.6 * inch, "Body Systems Learning Hub")
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 2.2 * inch, "Educational Certificate of Completion")

    c.setFont("Helvetica", 13)
    c.drawCentredString(width / 2, height - 3.1 * inch, "This certifies that")
    c.setFont("Helvetica-Bold", 17)
    c.drawCentredString(width / 2, height - 3.6 * inch, user.full_name or user.email)
    c.setFont("Helvetica", 13)
    c.drawCentredString(width / 2, height - 4.2 * inch, "has completed the educational pathway for")
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 4.7 * inch, system.name)

    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, 2.0 * inch, EDUCATIONAL_DISCLAIMER)
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, 1.5 * inch, f"Certificate No: {certificate_number}")
    c.drawCentredString(
      width / 2, 1.2 * inch, "MediMentora — AI-Powered Clinical Learning Platform"
    )

    c.showPage()
    c.save()
    return file_path
