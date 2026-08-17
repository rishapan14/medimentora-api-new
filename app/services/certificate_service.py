"""Certificate PDF generation."""

import os
import uuid

from flask import current_app
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


class CertificateService:
  @staticmethod
  def generate_certificate_pdf(user, course, certificate_number):
    folder = current_app.config["CERTIFICATE_UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)

    filename = f"cert_{certificate_number}.pdf"
    file_path = os.path.join(folder, filename)

    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width / 2, height - 2 * inch, "Certificate of Completion")

    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 3 * inch, "This certifies that")
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 3.5 * inch, user.full_name or user.email)
    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 4.2 * inch, "has successfully completed")
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 4.8 * inch, course.title)

    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, 1.5 * inch, f"Certificate No: {certificate_number}")
    c.drawCentredString(width / 2, 1.2 * inch, "AI-Powered Clinical Report Analysis & Nursing Assistance Platform")

    c.showPage()
    c.save()
    return file_path

  @staticmethod
  def generate_certificate_number():
    return f"CERT-{uuid.uuid4().hex[:12].upper()}"
