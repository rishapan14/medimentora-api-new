"""Post-OCR text normalization for medical reports."""

from __future__ import annotations

import re


# Common OCR misreads in lab reports
OCR_REPLACEMENTS = (
    (r"\bHe\s+moglobin\b", "Hemoglobin"),
    (r"\bHemoglubin\b", "Hemoglobin"),
    (r"\bHaemoglubin\b", "Haemoglobin"),
    (r"\bW8C\b", "WBC"),
    (r"\bWB\s+C\b", "WBC"),
    (r"\bR8C\b", "RBC"),
    (r"\bRB\s+C\b", "RBC"),
    (r"\bPLT\b", "Platelets"),
    (r"\bmg/d1\b", "mg/dL"),
    (r"\bg/d1\b", "g/dL"),
    (r"\bmg/dI\b", "mg/dL"),
    (r"\bu/L\b", "U/L"),
    (r"\b([0-9]+)\s*-\s*([0-9]+)\s*mg/dl\b", r"\1-\2 mg/dL"),
)

# Preserve lab lines: Name : value unit (optional range)
LAB_LINE_PATTERN = re.compile(
    r"^(.{2,40}?)\s*[:\-]\s*(\d+\.?\d*)\s*([A-Za-z/%µμ×\^0-9\.\-\s]{0,25})?\s*(?:\(([^)]+)\))?\s*$",
    re.IGNORECASE,
)


def clean_extracted_text(text: str) -> str:
    """
    Normalize OCR output while preserving lab values, units, and reference ranges.

    Steps: fix common OCR errors, dedupe lines, collapse excessive whitespace,
    preserve table-like lab rows.
    """
    if not text:
        return ""

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    for pattern, replacement in OCR_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    lines = []
    seen: set[str] = set()
    for raw_line in cleaned.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)

        lab_match = LAB_LINE_PATTERN.match(line)
        if lab_match:
            name, value, unit, ref = lab_match.groups()
            unit = (unit or "").strip()
            ref_part = f" ({ref.strip()})" if ref else ""
            line = f"{name.strip()}: {value} {unit}{ref_part}".strip()

        lines.append(line)

    return "\n".join(lines).strip()


def estimate_text_quality(text: str) -> float:
    """
    Heuristic OCR quality score in [0, 1] based on alphanumeric ratio and lab patterns.
    """
    if not text:
        return 0.0

    alnum = sum(ch.isalnum() or ch.isspace() for ch in text)
    ratio = alnum / max(len(text), 1)

    lab_hits = len(re.findall(r"(hemoglobin|wbc|rbc|glucose|creatinine|platelet|mg/dl|g/dl)", text, re.I))
    lab_bonus = min(lab_hits * 0.05, 0.25)

    word_count = len(text.split())
    length_bonus = min(word_count / 200, 0.2)

    return min(1.0, ratio * 0.65 + lab_bonus + length_bonus)
