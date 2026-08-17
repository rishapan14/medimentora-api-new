"""Export helpers for X-ray analysis (Module 8 — Patient Clinical Information).

Builds educational export payloads that always include patient clinical context
when available, plus a medical disclaimer. Never includes raw image bytes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER, XRAY_SHORT_DISCLAIMER, XrayAnalysis
from app.services.xray.safety_wording import hedge_finding_label, safety_payload


class XrayExportService:
  """Build JSON / text exports for an owned X-ray analysis."""

  @classmethod
  def build_json_payload(cls, row: XrayAnalysis) -> dict[str, Any]:
    xray = row.to_dict(include_explanation=True)
    # Strip server filesystem paths from educational exports
    for key in ("file_path", "preprocessed_path", "thumbnail_path"):
      xray.pop(key, None)

    ref_path = getattr(row, "reference_image_path", None)
    comparison_summary = getattr(row, "comparison_summary", None)
    comparison_generated_at = getattr(row, "comparison_generated_at", None)

    return {
      "exported_at": datetime.now(timezone.utc).isoformat(),
      "product": "MediMentora",
      "module": "ai_assisted_xray_analysis",
      "export_version": "1.2.0",
      "disclaimer": row.disclaimer or XRAY_MEDICAL_DISCLAIMER,
      "short_disclaimer": XRAY_SHORT_DISCLAIMER,
      "patient_clinical": row.patient_clinical_dict(),
      "safety": {
        **safety_payload(),
        "patient_clinical_supporting_context_only": True,
        "raw_image_included": False,
      },
      "comparison": {
        "reference_image_path": ref_path,
        "comparison_summary": comparison_summary,
        "comparison_generated_at": (
          comparison_generated_at.isoformat() if comparison_generated_at else None
        ),
        "has_comparison": bool(ref_path or comparison_summary),
      },
      "xray": xray,
    }

  @classmethod
  def build_text_summary(cls, row: XrayAnalysis) -> str:
    findings = row.possible_findings or []
    finding_lines = []
    for item in findings:
      if isinstance(item, dict):
        label = item.get("label") or item.get("finding") or "Finding"
        prob = item.get("probability")
        pct = ""
        if isinstance(prob, (int, float)):
          pct = f" ({round(max(0.0, min(1.0, float(prob))) * 100)}%)"
        finding_lines.append(f"- {hedge_finding_label(str(label))}{pct}")
      elif item is not None:
        finding_lines.append(f"- {hedge_finding_label(str(item))}")

    clinical = row.patient_clinical_dict()
    lines = [
      "MediMentora — AI-Assisted X-Ray Analysis Summary",
      XRAY_SHORT_DISCLAIMER,
      "",
      f"File: {row.filename or '—'}",
      f"Body part: {row.body_part or '—'}",
      f"Status: {row.status or '—'}",
      (
        f"Confidence: {round(float(row.confidence) * 100)}%"
        if row.confidence is not None
        else "Confidence: —"
      ),
      f"Model: {row.model_name or '—'}",
      f"Analysis version: {getattr(row, 'analysis_version', None) or '—'}",
      (
        "Specialist: "
        + str(
          (
            (getattr(row, "model_routing", None) or {}).get("specialist_key")
            if isinstance(getattr(row, "model_routing", None), dict)
            else None
          )
          or "—"
        )
      ),
      f"Analysis date: {row.analysis_date.isoformat() if row.analysis_date else '—'}",
      "",
      "Patient Clinical Information (supporting context only):",
      f"- Age: {clinical.get('patient_age') if clinical.get('patient_age') is not None else '—'}",
      f"- Gender: {clinical.get('gender') or '—'}",
      f"- Body part: {clinical.get('body_part') or '—'}",
      f"- Smoking history: {clinical.get('smoking_history') or '—'}",
      f"- Symptoms: {clinical.get('symptoms') or '—'}",
      f"- Reason for exam: {clinical.get('reason_for_exam') or '—'}",
      "",
      "Educational healthy comparison:",
      f"- Reference image: {getattr(row, 'reference_image_path', None) or '—'}",
      (
        f"- Comparison generated: "
        f"{getattr(row, 'comparison_generated_at', None).isoformat() if getattr(row, 'comparison_generated_at', None) else '—'}"
      ),
      getattr(row, "comparison_summary", None) or "(none)",
      "",
      "Possible findings:",
      *(finding_lines or ["- (none)"]),
      "",
      "AI summary:",
      row.ai_summary or "(none)",
      "",
    ]

    explanation = getattr(row, "structured_explanation", None)
    explanation = explanation if isinstance(explanation, dict) else {}
    if explanation:
      lines.extend(
        [
          "Educational explanation (Phase 12):",
          f"- Provider: {explanation.get('provider') or '—'}",
          f"- Fallback: {'yes' if explanation.get('used_fallback') else 'no'}",
          f"- Version: {explanation.get('explanation_version') or '—'}",
          "",
          "Patient-friendly:",
          explanation.get("patient_friendly_explanation") or "(none)",
          "",
          "Medical (educational):",
          explanation.get("medical_explanation") or "(none)",
          "",
          "Educational notes:",
          *(
            [f"- {n}" for n in (explanation.get("educational_notes") or [])]
            or ["- (none)"]
          ),
          "",
          "Lifestyle advice (general wellness only):",
          *(
            [f"- {n}" for n in (explanation.get("lifestyle_advice") or [])]
            or ["- (none)"]
          ),
          "",
          "Questions for a healthcare professional:",
          *(
            [
              f"- {n}"
              for n in (explanation.get("questions_for_healthcare_professional") or [])
            ]
            or ["- (none)"]
          ),
          "",
          "Explanation disclaimer:",
          explanation.get("disclaimer") or "(none)",
          "",
        ]
      )

    recs = getattr(row, "learning_recommendations", None)
    recs = recs if isinstance(recs, list) else []
    if recs:
      lines.append("Learning recommendations (Phase 13):")
      for rec in recs[:12]:
        if not isinstance(rec, dict):
          continue
        title = rec.get("title") or "Recommendation"
        rtype = rec.get("type") or "topic"
        reason = rec.get("reason") or ""
        href = rec.get("href") or ""
        flags = []
        if rec.get("clinical_aware"):
          flags.append("clinical")
        if rec.get("comparison_aware"):
          flags.append("comparison")
        flag_txt = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"- ({rtype}) {title}{flag_txt}")
        if reason:
          lines.append(f"  Reason: {reason}")
        if href:
          lines.append(f"  Link: {href}")
      lines.append("")

    lines.extend(
      [
        "Disclaimer:",
        row.disclaimer or XRAY_MEDICAL_DISCLAIMER,
        "",
        "Note: Patient clinical information is supporting context only and must not be "
        "treated as a confirmed diagnosis.",
        "",
      ]
    )
    return "\n".join(lines)

  @classmethod
  def build_pdf_report(cls, row: XrayAnalysis) -> bytes:
    """Build a PDF comparison report with patient info, reference metadata,
    AI comparison, recommendations, and medical disclaimer."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
      Paragraph,
      SimpleDocTemplate,
      Spacer,
      Table,
      TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
      buf,
      pagesize=A4,
      rightMargin=40,
      leftMargin=40,
      topMargin=40,
      bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    heading = styles["Heading2"]
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=10, textColor=colors.grey)
    bullet = ParagraphStyle("Bullet", parent=normal, fontSize=9, leading=12, leftIndent=18)

    elements: list = []

    # Title
    elements.append(Paragraph("MediMentora — X-Ray Comparison Report", styles["Title"]))
    elements.append(Paragraph(
      f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
      small,
    ))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
      XRAY_SHORT_DISCLAIMER,
      ParagraphStyle("Warn", parent=normal, fontSize=9, textColor=colors.HexColor("#B45309")),
    ))
    elements.append(Spacer(1, 0.25 * inch))

    # Patient information
    clinical = row.patient_clinical_dict()
    elements.append(Paragraph("Patient Information", heading))
    patient_data = [
      ["File", row.filename or "—"],
      ["Body part", row.body_part or "—"],
      ["Age", str(clinical.get("patient_age")) if clinical.get("patient_age") is not None else "—"],
      ["Gender", clinical.get("gender") or "—"],
      ["Smoking", clinical.get("smoking_history") or "—"],
      ["Symptoms", clinical.get("symptoms") or "—"],
      ["Reason for exam", clinical.get("reason_for_exam") or "—"],
      ["Confidence", f"{round(float(row.confidence) * 100)}%" if row.confidence is not None else "—"],
      ["Model", row.model_name or "—"],
      ["Analysis version", getattr(row, "analysis_version", None) or "—"],
      [
        "Specialist",
        str(
          (
            (getattr(row, "model_routing", None) or {}).get("specialist_key")
            if isinstance(getattr(row, "model_routing", None), dict)
            else None
          )
          or "—"
        ),
      ],
    ]
    t = Table(patient_data, colWidths=[1.6 * inch, 4.8 * inch])
    t.setStyle(TableStyle([
      ("FONTSIZE", (0, 0), (-1, -1), 9),
      ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
      ("VALIGN", (0, 0), (-1, -1), "TOP"),
      ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.2 * inch))

    # Reference metadata
    ref_path = getattr(row, "reference_image_path", None)
    explanation = getattr(row, "structured_explanation", None)
    explanation = explanation if isinstance(explanation, dict) else {}
    ref_meta = explanation.get("comparison_reference") or {}
    if ref_path or ref_meta:
      elements.append(Paragraph("Healthy Reference Image", heading))
      ref_data = [
        ["Body part", ref_meta.get("body_part") or "—"],
        ["Projection", ref_meta.get("projection") or "—"],
        ["Age group", ref_meta.get("age_group") or "—"],
        ["Gender", ref_meta.get("gender") or "—"],
      ]
      t2 = Table(ref_data, colWidths=[1.6 * inch, 4.8 * inch])
      t2.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
      ]))
      elements.append(t2)
      elements.append(Spacer(1, 0.2 * inch))

    # AI educational comparison
    structured = explanation.get("educational_comparison") or {}
    if isinstance(structured, dict):
      elements.append(Paragraph("AI Educational Comparison", heading))
      summary = structured.get("comparison_summary") or getattr(row, "comparison_summary", None) or ""
      if summary:
        elements.append(Paragraph(summary, normal))
        elements.append(Spacer(1, 0.1 * inch))

      for section_key, section_title in [
        ("key_visual_differences", "Key Visual Differences"),
        ("normal_anatomical_landmarks", "Normal Anatomical Landmarks"),
        ("learning_focus", "Learning Focus"),
        ("questions_for_healthcare_professional", "Questions for Healthcare Professional"),
      ]:
        items = structured.get(section_key) or []
        if items:
          elements.append(Paragraph(section_title, ParagraphStyle(
            "SubHead", parent=normal, fontSize=10, spaceAfter=4, spaceBefore=8,
            textColor=colors.HexColor("#1E3A5F"),
          )))
          for item in items[:8]:
            elements.append(Paragraph(f"• {item}", bullet))

      discussion = structured.get("possible_findings_discussion")
      if discussion:
        elements.append(Spacer(1, 0.08 * inch))
        elements.append(Paragraph("Possible Findings Discussion", ParagraphStyle(
          "SubHead2", parent=normal, fontSize=10, spaceAfter=4, spaceBefore=8,
          textColor=colors.HexColor("#1E3A5F"),
        )))
        elements.append(Paragraph(discussion, normal))

      elements.append(Spacer(1, 0.2 * inch))

    # Possible findings
    findings = getattr(row, "possible_findings", None) or []
    if findings:
      elements.append(Paragraph("Possible Findings", heading))
      for item in findings:
        if isinstance(item, dict):
          label = item.get("label") or item.get("finding") or "Finding"
          prob = item.get("probability")
          pct = f" ({round(max(0.0, min(1.0, float(prob))) * 100)}%)" if isinstance(prob, (int, float)) else ""
          elements.append(Paragraph(f"• {hedge_finding_label(str(label))}{pct}", bullet))
        elif item is not None:
          elements.append(Paragraph(f"• {hedge_finding_label(str(item))}", bullet))
      elements.append(Spacer(1, 0.2 * inch))

    # Learning recommendations
    recs = getattr(row, "learning_recommendations", None)
    recs = recs if isinstance(recs, list) else []
    if recs:
      elements.append(Paragraph("Learning Recommendations", heading))
      for rec in recs[:8]:
        if isinstance(rec, dict):
          title = rec.get("title") or "—"
          reason = rec.get("reason") or ""
          elements.append(Paragraph(f"• <b>{title}</b>", bullet))
          if reason:
            elements.append(Paragraph(f"  {reason}", ParagraphStyle(
              "Reason", parent=bullet, fontSize=8, textColor=colors.grey,
            )))
      elements.append(Spacer(1, 0.2 * inch))

    # Disclaimer
    elements.append(Paragraph("Medical Disclaimer", heading))
    elements.append(Paragraph(
      row.disclaimer or XRAY_MEDICAL_DISCLAIMER,
      ParagraphStyle("Disclaimer", parent=normal, fontSize=8, leading=10, textColor=colors.HexColor("#B45309")),
    ))

    doc.build(elements)
    return buf.getvalue()

  @classmethod
  def export(cls, row: XrayAnalysis, fmt: str) -> tuple[str | bytes, str, str]:
    """
    Returns (content, mimetype, download_filename).

    fmt: json | txt | summary | pdf
    """
    kind = (fmt or "json").strip().lower()
    if kind == "pdf":
      content = cls.build_pdf_report(row)
      return content, "application/pdf", f"xray_{row.id}_comparison_report.pdf"

    if kind in ("txt", "text", "summary"):
      content = cls.build_text_summary(row)
      return content, "text/plain; charset=utf-8", f"xray_{row.id}_summary.txt"

    import json

    payload = cls.build_json_payload(row)
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return content, "application/json; charset=utf-8", f"xray_{row.id}_analysis.json"
