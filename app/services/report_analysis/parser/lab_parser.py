"""Parse laboratory values and reference ranges from medical report text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedLabValue:
    name: str
    value: str
    numeric: float
    unit: str
    normal_range: str
    status: str  # normal | low | high | borderline | unknown
    significance: str
    explanation: str
    source: str = "extracted"


@dataclass
class ParseResult:
    values: list[ParsedLabValue] = field(default_factory=list)
    report_type: str = "general"
    patient_hints: dict = field(default_factory=dict)

    @property
    def abnormal(self) -> list[ParsedLabValue]:
        return [v for v in self.values if v.status in ("low", "high", "borderline")]

    @property
    def normal(self) -> list[ParsedLabValue]:
        return [v for v in self.values if v.status == "normal"]


# Canonical test definitions
TEST_DEFINITIONS: dict[str, dict] = {
    "hemoglobin": {
        "label": "Hemoglobin",
        "aliases": ("hemoglobin", "haemoglobin", "hgb", "hb"),
        "unit": "g/dL",
        "low": 12.0,
        "high": 16.0,
        "explanation": "Protein in red blood cells that carries oxygen throughout the body.",
    },
    "wbc": {
        "label": "WBC",
        "aliases": ("wbc", "white blood cell", "white blood cells", "leukocyte", "leukocytes"),
        "unit": "×10³/µL",
        "low": 4.0,
        "high": 11.0,
        "scale": "wbc",
        "explanation": "White blood cells help the body fight infection.",
    },
    "rbc": {
        "label": "RBC",
        "aliases": ("rbc", "red blood cell", "red blood cells", "erythrocyte"),
        "unit": "×10⁶/µL",
        "low": 4.2,
        "high": 5.9,
        "scale": "rbc",
        "explanation": "Red blood cells carry oxygen to tissues.",
    },
    "platelets": {
        "label": "Platelets",
        "aliases": ("platelet", "platelets", "plt", "thrombocyte"),
        "unit": "×10³/µL",
        "low": 150.0,
        "high": 400.0,
        "scale": "platelet",
        "explanation": "Platelets help blood clot to stop bleeding.",
    },
    "glucose": {
        "label": "Glucose",
        "aliases": ("glucose", "blood sugar", "fasting glucose", "random glucose"),
        "unit": "mg/dL",
        "low": 70.0,
        "high": 100.0,
        "explanation": "Blood sugar level; important for energy metabolism.",
    },
    "creatinine": {
        "label": "Creatinine",
        "aliases": ("creatinine", "serum creatinine"),
        "unit": "mg/dL",
        "low": 0.7,
        "high": 1.3,
        "explanation": "Waste product filtered by the kidneys; reflects kidney function.",
    },
    "hematocrit": {
        "label": "Hematocrit",
        "aliases": ("hematocrit", "hct", "pcv"),
        "unit": "%",
        "low": 36.0,
        "high": 48.0,
        "explanation": "Percentage of blood volume occupied by red blood cells.",
    },
    "ldl": {
        "label": "LDL Cholesterol",
        "aliases": ("ldl", "ldl cholesterol", "ldl-c"),
        "unit": "mg/dL",
        "low": 0.0,
        "high": 100.0,
        "explanation": "Low-density lipoprotein; higher levels increase cardiovascular risk.",
    },
    "hdl": {
        "label": "HDL Cholesterol",
        "aliases": ("hdl", "hdl cholesterol", "hdl-c"),
        "unit": "mg/dL",
        "low": 40.0,
        "high": 999.0,
        "invert": True,
        "explanation": "High-density lipoprotein; higher levels are generally protective.",
    },
    "total_cholesterol": {
        "label": "Total Cholesterol",
        "aliases": ("total cholesterol", "cholesterol total", "serum cholesterol"),
        "unit": "mg/dL",
        "low": 0.0,
        "high": 200.0,
        "explanation": "Total cholesterol in the blood.",
    },
    "triglycerides": {
        "label": "Triglycerides",
        "aliases": ("triglycerides", "triglyceride", "tg"),
        "unit": "mg/dL",
        "low": 0.0,
        "high": 150.0,
        "explanation": "Type of fat in the blood; elevated levels may increase heart disease risk.",
    },
    "tsh": {
        "label": "TSH",
        "aliases": ("tsh", "thyroid stimulating hormone"),
        "unit": "mIU/L",
        "low": 0.4,
        "high": 4.0,
        "explanation": "Thyroid stimulating hormone; screens thyroid function.",
    },
    "alt": {
        "label": "ALT",
        "aliases": ("alt", "sgpt", "alanine aminotransferase"),
        "unit": "U/L",
        "low": 7.0,
        "high": 56.0,
        "explanation": "Liver enzyme; elevated levels may indicate liver stress or damage.",
    },
    "ast": {
        "label": "AST",
        "aliases": ("ast", "sgot", "aspartate aminotransferase"),
        "unit": "U/L",
        "low": 10.0,
        "high": 40.0,
        "explanation": "Enzyme found in liver and other tissues; may rise with liver or muscle injury.",
    },
}

LINE_PATTERN = re.compile(
    r"^(.{2,45}?)\s*[:\-]\s*(\d+\.?\d*)\s*([A-Za-z/%µμ×\^0-9\.\-\s]{0,20})?\s*(?:\(([^)]+)\))?\s*$",
    re.IGNORECASE,
)

INLINE_PATTERN = re.compile(
    r"(hemoglobin|haemoglobin|hgb|wbc|white blood cells?|rbc|platelets?|glucose|creatinine|"
    r"hematocrit|ldl|hdl|triglycerides?|tsh|alt|ast|cholesterol)\s*[:\-]?\s*"
    r"(\d+\.?\d*)\s*([A-Za-z/%µμ×\^0-9\.\-\s]{0,15})?(?:\(([^)]+)\))?",
    re.IGNORECASE,
)


def _normalize_name(name: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", name.strip().lower())
    for key, meta in TEST_DEFINITIONS.items():
        if cleaned == key or cleaned in meta["aliases"]:
            return key
        for alias in meta["aliases"]:
            if alias in cleaned or cleaned in alias:
                return key
    return None


def _parse_reference_range(ref: str | None) -> tuple[float | None, float | None, str]:
    if not ref:
        return None, None, ""
    ref = ref.strip()
    if match := re.match(r"<\s*(\d+\.?\d*)", ref):
        return None, float(match.group(1)), ref
    if match := re.match(r">\s*(\d+\.?\d*)", ref):
        return float(match.group(1)), None, ref
    if match := re.match(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", ref):
        return float(match.group(1)), float(match.group(2)), ref
    return None, None, ref


def _scale_value(value: float, scale: str | None) -> float:
    if scale == "wbc" and value > 100:
        return round(value / 1000, 2)
    if scale == "platelet" and value > 1000:
        return round(value / 1000, 1)
    if scale == "rbc" and value > 20:
        return round(value / 1000000, 2)
    return value


def _classify(
    numeric: float,
    low: float,
    high: float,
    invert: bool = False,
    ref_low: float | None = None,
    ref_high: float | None = None,
) -> tuple[str, str]:
    low_bound = ref_low if ref_low is not None else low
    high_bound = ref_high if ref_high is not None else high

    if invert:
        if numeric < low_bound:
            return "low", f"Below desirable level (reference: ≥{low_bound:g})."
        return "normal", "Within desirable range."

    if high_bound and numeric > high_bound * 1.25:
        return "high", f"Markedly above normal (reference: {low_bound:g}-{high_bound:g})."
    if low_bound and numeric < low_bound * 0.85:
        return "low", f"Markedly below normal (reference: {low_bound:g}-{high_bound:g})."
    if numeric < low_bound:
        return "borderline" if numeric >= low_bound * 0.95 else "low", f"Below normal (reference: {low_bound:g}-{high_bound:g})."
    if numeric > high_bound:
        return "borderline" if numeric <= high_bound * 1.05 else "high", f"Above normal (reference: {low_bound:g}-{high_bound:g})."
    return "normal", "Within normal range."


def parse_medical_report(text: str) -> ParseResult:
    """Extract and classify laboratory values from report text."""
    if not text:
        return ParseResult()

    result = ParseResult()
    seen: set[str] = set()

    # Line-by-line parsing (best for OCR output)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LINE_PATTERN.match(line)
        if not match:
            continue

        name_raw, val_str, unit, ref = match.groups()
        test_key = _normalize_name(name_raw)
        if not test_key or test_key in seen:
            continue

        seen.add(test_key)
        meta = TEST_DEFINITIONS[test_key]
        numeric = _scale_value(float(val_str), meta.get("scale"))
        unit = (unit or meta["unit"]).strip() or meta["unit"]
        ref_low, ref_high, ref_display = _parse_reference_range(ref)
        normal_display = ref_display or f"{meta['low']}-{meta['high']} {meta['unit']}"

        status, significance = _classify(
            numeric,
            meta["low"],
            meta["high"],
            invert=meta.get("invert", False),
            ref_low=ref_low,
            ref_high=ref_high,
        )

        result.values.append(
            ParsedLabValue(
                name=meta["label"],
                value=f"{numeric:g} {unit}".strip(),
                numeric=numeric,
                unit=unit,
                normal_range=normal_display,
                status=status,
                significance=significance,
                explanation=meta["explanation"],
            )
        )

    # Inline fallback for unstructured text
    if not result.values:
        for match in INLINE_PATTERN.finditer(text):
            name_raw, val_str, unit, ref = match.groups()
            test_key = _normalize_name(name_raw)
            if not test_key or test_key in seen:
                continue
            seen.add(test_key)
            meta = TEST_DEFINITIONS[test_key]
            numeric = _scale_value(float(val_str), meta.get("scale"))
            ref_low, ref_high, ref_display = _parse_reference_range(ref)
            status, significance = _classify(
                numeric, meta["low"], meta["high"],
                invert=meta.get("invert", False),
                ref_low=ref_low, ref_high=ref_high,
            )
            result.values.append(
                ParsedLabValue(
                    name=meta["label"],
                    value=f"{numeric:g} {(unit or meta['unit']).strip()}".strip(),
                    numeric=numeric,
                    unit=(unit or meta["unit"]).strip(),
                    normal_range=ref_display or f"{meta['low']}-{meta['high']} {meta['unit']}",
                    status=status,
                    significance=significance,
                    explanation=meta["explanation"],
                )
            )

    # Detect report type
    names = " ".join(v.name.lower() for v in result.values)
    if any(k in names for k in ("hemoglobin", "wbc", "platelet")):
        result.report_type = "cbc"
    elif any(k in names for k in ("ldl", "hdl", "cholesterol", "triglyceride")):
        result.report_type = "lipid_profile"
    elif "glucose" in names:
        result.report_type = "blood_sugar"
    elif any(k in names for k in ("alt", "ast")):
        result.report_type = "liver_function"

    return result


def parsed_to_analysis_dict(parsed: ParseResult) -> dict:
    """Convert parse result to analysis API shape."""
    abnormal = parsed.abnormal
    normal = parsed.normal

    if not parsed.values:
        return {
            "simple_explanation": "",
            "abnormal_values": [],
            "normal_values": [],
            "possible_diseases": [],
            "medical_terms": [],
            "learning_topics": [],
            "parsed_tests": [],
        }

    if abnormal:
        summary_parts = [f"{v.name} {v.value} ({v.significance})" for v in abnormal]
        explanation = (
            f"This report appears to be a {parsed.report_type.replace('_', ' ')} panel. "
            f"{len(abnormal)} result(s) fall outside the reference range: {'; '.join(summary_parts)}. "
            f"{len(normal)} result(s) are within normal limits. "
            "This analysis is for educational purposes only and is not a medical diagnosis."
        )
    else:
        explanation = (
            f"This report appears to be a {parsed.report_type.replace('_', ' ')} panel. "
            f"All {len(normal)} parsed value(s) appear within their reference ranges. "
            "This analysis is for educational purposes only and is not a medical diagnosis."
        )

    return {
        "simple_explanation": explanation,
        "abnormal_values": [
            {
                "name": v.name,
                "value": v.value,
                "normal_range": v.normal_range,
                "significance": v.significance,
                "status": v.status,
            }
            for v in abnormal
        ],
        "normal_values": [
            {
                "name": v.name,
                "value": v.value,
                "normal_range": v.normal_range,
                "significance": v.significance,
            }
            for v in normal
        ],
        "medical_terms": [{"term": v.name, "explanation": v.explanation} for v in parsed.values],
        "learning_topics": list({v.name for v in parsed.values[:5]}),
        "parsed_tests": [
            {"name": v.name, "value": v.value, "status": v.status, "normal_range": v.normal_range}
            for v in parsed.values
        ],
        "report_type": parsed.report_type,
    }
