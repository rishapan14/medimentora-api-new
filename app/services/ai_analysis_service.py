"""OpenAI-powered medical report analysis with local fallback parsing."""

import json
import re

from flask import current_app

from app.services.report_analysis.parser import parse_medical_report, parsed_to_analysis_dict


class AIAnalysisService:
    """Send report text to OpenAI and parse structured analysis."""

    SYSTEM_PROMPT = (
        "You are a clinical education assistant for nurses and medical students. "
        "You will receive verified lab values extracted from a report plus the raw text. "
        "Use ONLY those values — do NOT invent tests or numbers. "
        "If a value is within its reference range, do not list it under abnormal_values. "
        "Respond ONLY with valid JSON using this schema:\n"
        "{\n"
        '  "simple_explanation": "plain language summary of the actual findings",\n'
        '  "abnormal_values": [{"name": "", "value": "", "normal_range": "", "significance": ""}],\n'
        '  "possible_diseases": [{"disease": "", "likelihood": "low|medium|high", "reasoning": ""}],\n'
        '  "medical_terms": [{"term": "", "explanation": ""}],\n'
        '  "learning_topics": ["topic1", "topic2"]\n'
        "}\n"
        "Do not include markdown or extra text outside the JSON."
    )

    @classmethod
    def analyze_report(cls, report_text):
        cleaned = cls._normalize_report_text(report_text)
        if not cleaned or len(cleaned.strip()) < 10:
            raise ValueError(
                "Not enough text was extracted from this report to analyze. "
                "Upload a clearer PDF/image or ensure OCR completed successfully."
            )

        parsed = parse_medical_report(cleaned)
        local = parsed_to_analysis_dict(parsed)
        local["analysis_mode"] = "local"
        local["possible_diseases"] = cls._infer_conditions(local.get("abnormal_values") or [])

        api_key = current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            if not parsed.values:
                preview = cleaned[:300].strip()
                local["simple_explanation"] = (
                    "Could not identify structured lab values in the extracted text. "
                    "Try a clearer PDF/image, or add OPENAI_API_KEY to .env for full AI analysis.\n\n"
                    f"Extracted text preview: {preview}"
                )
            return local

        try:
            from openai import OpenAI
        except ImportError:
            return local

        verified = [
            {"name": v.name, "value": v.value, "status": v.status, "normal_range": v.normal_range}
            for v in parsed.values
        ]
        user_content = (
            "Verified extracted values (ground truth — do not contradict these):\n"
            f"{json.dumps(verified, indent=2)}\n\n"
            f"Raw report text:\n{cleaned}"
        )

        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": cls.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            ai_data = json.loads(content)
            merged = cls._merge_with_local(ai_data, local)
            merged["analysis_mode"] = "openai"
            return merged
        except Exception:
            return local

    @staticmethod
    def _normalize_report_text(text: str) -> str:
        """Fix common OCR mistakes while preserving line structure for parsing."""
        if not text:
            return ""

        normalized = text
        ocr_fixes = (
            (r"\bHe\s+moglobin\b", "Hemoglobin"),
            (r"\bHemoglubin\b", "Hemoglobin"),
            (r"\bHaemoglubin\b", "Haemoglobin"),
            (r"\bW8C\b", "WBC"),
            (r"\bWB\s+C\b", "WBC"),
            (r"[ \t]+", " "),
        )
        for pattern, replacement in ocr_fixes:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        # Collapse excessive blank lines but keep one newline per lab row
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @classmethod
    def _merge_with_local(cls, ai_data: dict, local: dict) -> dict:
        """Prefer locally parsed values for abnormal/normal lists; enrich with AI narrative."""
        merged = {**local, **ai_data}
        merged["abnormal_values"] = local.get("abnormal_values") or ai_data.get("abnormal_values") or []
        merged["normal_values"] = local.get("normal_values") or []
        merged["parsed_tests"] = local.get("parsed_tests") or []

        if local.get("abnormal_values"):
            merged["simple_explanation"] = ai_data.get("simple_explanation") or local.get("simple_explanation")
        elif not ai_data.get("simple_explanation"):
            merged["simple_explanation"] = local.get("simple_explanation")

        if not merged.get("possible_diseases"):
            merged["possible_diseases"] = cls._infer_conditions(merged.get("abnormal_values") or [])

        if not merged.get("medical_terms") and local.get("medical_terms"):
            merged["medical_terms"] = local["medical_terms"]

        return merged

    @staticmethod
    def _infer_conditions(abnormal: list[dict]) -> list[dict]:
        """Educational condition hints from abnormal labs only."""
        hints = []
        by_name = {str(f.get("name", "")).lower(): f for f in abnormal}

        hb = by_name.get("hemoglobin")
        if hb and str(hb.get("status", "")).lower() in ("low", "borderline"):
            hints.append(
                {
                    "disease": "Anemia (possible)",
                    "likelihood": "medium",
                    "reasoning": "Low hemoglobin may suggest anemia; correlate with symptoms and iron studies.",
                }
            )

        hct = by_name.get("hematocrit")
        if hct and str(hct.get("status", "")).lower() in ("low", "borderline") and not hb:
            hints.append(
                {
                    "disease": "Anemia (possible)",
                    "likelihood": "medium",
                    "reasoning": "Low hematocrit may suggest anemia or dehydration.",
                }
            )

        wbc = by_name.get("wbc")
        if wbc:
            status = str(wbc.get("status", "")).lower()
            if status == "high":
                hints.append(
                    {
                        "disease": "Infection or inflammation (possible)",
                        "likelihood": "medium",
                        "reasoning": "Elevated WBC often associated with infection, stress, or inflammation.",
                    }
                )
            elif status in ("low", "borderline"):
                hints.append(
                    {
                        "disease": "Leukopenia (possible)",
                        "likelihood": "low",
                        "reasoning": "Low WBC may occur with viral illness, bone marrow suppression, or certain medications.",
                    }
                )

        glucose = by_name.get("glucose")
        if glucose and str(glucose.get("status", "")).lower() in ("high", "borderline"):
            hints.append(
                {
                    "disease": "Hyperglycemia (possible)",
                    "likelihood": "medium",
                    "reasoning": "Elevated glucose may indicate poor glycemic control or need for diabetes screening.",
                }
            )

        creat = by_name.get("creatinine")
        if creat and str(creat.get("status", "")).lower() in ("high", "borderline"):
            hints.append(
                {
                    "disease": "Reduced kidney function (possible)",
                    "likelihood": "medium",
                    "reasoning": "Elevated creatinine may reflect impaired renal function.",
                }
            )

        ldl = by_name.get("ldl cholesterol")
        if ldl and str(ldl.get("status", "")).lower() in ("high", "borderline"):
            hints.append(
                {
                    "disease": "Dyslipidemia (possible)",
                    "likelihood": "medium",
                    "reasoning": "Elevated LDL cholesterol increases cardiovascular risk.",
                }
            )

        if not hints and abnormal:
            hints.append(
                {
                    "disease": "Further clinical correlation needed",
                    "likelihood": "low",
                    "reasoning": "Abnormal values were detected; review with a clinician and the original report.",
                }
            )

        return hints

    @classmethod
    def simulation_feedback(cls, scenario, diagnosis, treatment, correct_diagnosis, correct_treatment):
        """Generate immediate AI feedback for simulation attempts."""
        fallback = cls.local_simulation_feedback(
            diagnosis, treatment, correct_diagnosis, correct_treatment
        )
        api_key = current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            return fallback

        try:
            from openai import OpenAI
        except ImportError:
            return fallback

        client = OpenAI(api_key=api_key)
        prompt = (
            f"Patient scenario: {scenario}\n"
            f"Student diagnosis: {diagnosis}\n"
            f"Student treatment: {treatment}\n"
            f"Correct diagnosis: {correct_diagnosis}\n"
            f"Correct treatment: {correct_treatment}\n\n"
            "Provide constructive clinical feedback and a score 0-100 as JSON: "
            '{"feedback": "...", "score": 85}'
        )
        try:
            response = client.chat.completions.create(
                model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            score = float(result.get("score", 0))
            feedback = str(result.get("feedback") or "").strip()
            if not feedback:
                return fallback
            return {"feedback": feedback, "score": max(0, min(100, score))}
        except Exception:
            return fallback

    @staticmethod
    def _answers_match(selected, expected):
        """Compare clinical choices while tolerating punctuation and concise option labels."""
        selected_tokens = set(re.findall(r"[a-z0-9]+", str(selected or "").casefold()))
        expected_tokens = set(re.findall(r"[a-z0-9]+", str(expected or "").casefold()))
        ignored = {"a", "an", "and", "or", "the", "therapy", "treatment"}
        selected_tokens -= ignored
        expected_tokens -= ignored
        if not selected_tokens or not expected_tokens:
            return False
        if selected_tokens == expected_tokens:
            return True
        overlap = len(selected_tokens & expected_tokens)
        return (
            overlap / len(selected_tokens) >= 0.75
            and overlap / len(expected_tokens) >= 0.5
        )

    @classmethod
    def local_simulation_feedback(
        cls, diagnosis, treatment, correct_diagnosis, correct_treatment
    ):
        """Return deterministic feedback so simulations work without an AI provider."""
        diagnosis_correct = cls._answers_match(diagnosis, correct_diagnosis)
        treatment_correct = cls._answers_match(treatment, correct_treatment)
        score = (50 if diagnosis_correct else 0) + (50 if treatment_correct else 0)
        return {
            "feedback": (
                "Offline fallback feedback: "
                f"Your diagnosis was {'correct' if diagnosis_correct else 'incorrect'} and "
                f"your treatment was {'correct' if treatment_correct else 'incorrect'}. "
                f"Correct diagnosis: {correct_diagnosis}. "
                f"Correct treatment: {correct_treatment}."
            ),
            "score": score,
        }
