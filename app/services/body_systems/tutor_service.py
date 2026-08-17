"""AI Tutor for Body Systems Learning Hub (Phase 6).

Uses lesson/organ/system structured content as the primary context source.
Educational only — never diagnoses or prescribes.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.services.body_systems.hub_service import BodySystemHubService
from app.services.medical_teacher.ai_client import TeacherAIClient
from app.services.xray.safety_wording import ensure_short_disclaimer, sanitize_educational_text

logger = logging.getLogger(__name__)

TUTOR_VERSION = "phase6-v1"

TUTOR_MODES: dict[str, dict[str, str]] = {
  "explain_simply": {
    "label": "Explain simply",
    "instruction": "Explain the topic in plain, simple language for a first-year learner.",
  },
  "beginner": {
    "label": "Explain for beginners",
    "instruction": "Explain for absolute beginners with no assumed medical background.",
  },
  "nursing": {
    "label": "Explain for nursing students",
    "instruction": "Explain with nursing-student focus: assessment cues, priorities, and patient education themes.",
  },
  "examples": {
    "label": "Explain with examples",
    "instruction": "Explain using concrete clinical-education examples (not real patient advice).",
  },
  "mnemonics": {
    "label": "Mnemonics",
    "instruction": "Teach with memorable mnemonics and memory tricks grounded in the provided context.",
  },
  "english": {
    "label": "Explain in English",
    "instruction": "Respond in clear English suitable for medical education.",
  },
  "tamil": {
    "label": "Explain in Tamil",
    "instruction": "Respond primarily in Tamil (தமிழ்), keeping key medical terms in English in parentheses when helpful.",
  },
  "practice_questions": {
    "label": "Practice questions",
    "instruction": "Generate 5 educational practice questions (mix of MCQ and short answer) with brief rationales. Mark answers clearly.",
  },
  "flashcards": {
    "label": "Generate flashcards",
    "instruction": "Generate 6 educational flashcards as front/back pairs for revision.",
  },
  "exam_notes": {
    "label": "Exam notes",
    "instruction": "Produce concise exam-revision notes: high-yield bullets, must-know lists, and pitfalls.",
  },
  "one_minute_summary": {
    "label": "1-minute summary",
    "instruction": "Write a 1-minute spoken-style summary a student could read aloud.",
  },
  "five_minute_revision": {
    "label": "5-minute revision",
    "instruction": "Write a structured 5-minute revision sheet covering the essentials.",
  },
  "viva_questions": {
    "label": "Viva questions",
    "instruction": "Generate 5 oral-exam (viva) style educational questions with model answers and brief examiner tips. Stay grounded in the lesson context.",
  },
  "ask": {
    "label": "Ask a question",
    "instruction": "Answer the learner question using ONLY the provided lesson context. If unknown from context, say so and stay educational.",
  },
}

SYSTEM_PROMPT = """You are MediMentora's AI Tutor for the Human Body Systems Learning Hub.

HARD RULES:
1. Educational use only — never claim a diagnosis for a real patient.
2. Never prescribe medication, dosages, or specific treatment plans as clinical advice.
3. Use the provided lesson/organ/system CONTEXT as the primary source of truth.
4. Do not invent anatomy facts that contradict the context; if context is thin, say what is known educationally and stay cautious.
5. Always end with a short educational disclaimer.
6. Frame disease content as learning topics, not personal medical advice.

Return ONLY valid JSON:
{
  "title": "string",
  "answer": "string — main tutoring response (markdown allowed)",
  "bullets": ["optional key points"],
  "flashcards": [{"front": "string", "back": "string"}],
  "questions": [{"prompt": "string", "answer": "string", "rationale": "string"}],
  "mnemonics": ["string"],
  "disclaimer": "string — educational / not a diagnosis"
}
"""


class HubAiTutorService:
  """Context-grounded educational tutor for organs and body systems."""

  @classmethod
  def list_modes(cls) -> list[dict[str, str]]:
    return [{"id": key, "label": meta["label"]} for key, meta in TUTOR_MODES.items()]

  @classmethod
  def tutor(
    cls,
    *,
    mode: str = "explain_simply",
    message: str | None = None,
    organ_slug: str | None = None,
    system_slug: str | None = None,
    language: str | None = None,
    source: str | None = None,
  ) -> tuple[dict[str, Any] | None, str]:
    """
    Returns (payload, error_code).
    error_code: ok | validation_error | not_found
    """
    mode_key = (mode or "explain_simply").strip().lower()
    if mode_key not in TUTOR_MODES:
      return None, "validation_error"
    if not organ_slug and not system_slug:
      return None, "validation_error"

    context, meta = cls._build_context(organ_slug=organ_slug, system_slug=system_slug)
    if context is None:
      return None, "not_found"

    source_key = (source or "").strip().lower()
    if source_key in ("anatomy_3d", "explorer_3d", "3d"):
      context["viewer"] = "anatomy_3d_explorer"
      context["viewer_note"] = (
        "The learner selected this structure in the 3D Human Body Explorer. "
        "Prefer spatial/anatomy cues and keep answers educational."
      )
      meta["source"] = "anatomy_3d"

    # Language shortcuts map onto modes when provided
    lang = (language or "").strip().lower()
    if lang in ("ta", "tamil") and mode_key in ("explain_simply", "beginner", "english", "ask"):
      mode_key = "tamil"
    elif lang in ("en", "english") and mode_key == "tamil":
      mode_key = "english"

    instruction = TUTOR_MODES[mode_key]["instruction"]
    user_question = (message or "").strip()
    if mode_key == "ask" and not user_question:
      user_question = "Please teach the most important educational points from this context."

    started = time.perf_counter()
    user_prompt = (
      f"MODE: {mode_key}\n"
      f"INSTRUCTION: {instruction}\n"
      f"LEARNER_QUESTION: {user_question or '(none — follow mode instruction)'}\n\n"
      f"CONTEXT_JSON:\n{json.dumps(context, ensure_ascii=False)[:12000]}\n"
    )

    data, provider = TeacherAIClient.complete_json(SYSTEM_PROMPT, user_prompt)
    used_fallback = False
    if not data:
      data = cls._offline_fallback(mode_key, context, user_question)
      provider = "offline"
      used_fallback = True

    payload = cls._normalize_payload(
      data,
      mode=mode_key,
      provider=provider,
      used_fallback=used_fallback,
      meta=meta,
      processing_ms=int((time.perf_counter() - started) * 1000),
    )
    return payload, "ok"

  @classmethod
  def _build_context(
    cls, *, organ_slug: str | None, system_slug: str | None
  ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    meta: dict[str, Any] = {"organ_slug": None, "system_slug": None, "scope": None}
    if organ_slug:
      organ = BodySystemHubService.get_organ(organ_slug, system_slug=system_slug)
      if not organ:
        return None, meta
      meta.update(
        {
          "organ_slug": organ.get("slug"),
          "system_slug": (organ.get("body_system") or {}).get("slug"),
          "scope": "organ",
          "title": organ.get("name"),
        }
      )
      return {
        "type": "organ",
        "name": organ.get("name"),
        "slug": organ.get("slug"),
        "location": organ.get("location"),
        "learning_objectives": organ.get("learning_objectives") or [],
        "sections": organ.get("sections") or {},
        "body_system": organ.get("body_system"),
        "safety": organ.get("safety"),
      }, meta

    system = BodySystemHubService.get_system(system_slug or "")
    if not system:
      return None, meta
    meta.update(
      {
        "system_slug": system.get("slug"),
        "scope": "body_system",
        "title": system.get("name"),
      }
    )
    organs = [
      {
        "slug": o.get("slug"),
        "name": o.get("name"),
        "short_description": o.get("short_description"),
        "location": o.get("location"),
      }
      for o in (system.get("organs") or [])[:12]
    ]
    return {
      "type": "body_system",
      "name": system.get("name"),
      "slug": system.get("slug"),
      "short_description": system.get("short_description"),
      "long_description": system.get("long_description"),
      "difficulty": system.get("difficulty"),
      "organs": organs,
      "safety": system.get("safety"),
    }, meta

  @classmethod
  def _offline_fallback(
    cls, mode: str, context: dict[str, Any], question: str
  ) -> dict[str, Any]:
    """Heuristic tutoring when Gemini/OpenAI are unavailable."""
    name = context.get("name") or "this topic"
    sections = context.get("sections") if isinstance(context.get("sections"), dict) else {}
    overview = sections.get("overview") or context.get("short_description") or f"Educational overview of {name}."
    functions = sections.get("functions") or []
    pearls = sections.get("clinical_pearls") or []
    objectives = context.get("learning_objectives") or []

    if mode in ("flashcards",):
      cards = []
      if overview:
        cards.append({"front": f"What is the {name}?", "back": str(overview)[:400]})
      for fn in functions[:4]:
        cards.append({"front": f"Function of {name}?", "back": str(fn)})
      for obj in objectives[:2]:
        cards.append({"front": "Learning objective", "back": str(obj)})
      return {
        "title": f"{name} flashcards",
        "answer": f"Generated educational flashcards for {name} (offline mode).",
        "flashcards": cards or [{"front": name, "back": overview}],
        "bullets": [],
        "questions": [],
        "mnemonics": [],
      }

    if mode in ("practice_questions", "viva_questions"):
      qs = [
        {
          "prompt": f"Name one primary educational function of the {name}.",
          "answer": str(functions[0]) if functions else "See lesson overview.",
          "rationale": "Grounded in lesson function list.",
        },
        {
          "prompt": f"Where is the {name} located (educational anatomy)?",
          "answer": str(sections.get("location") or context.get("location") or "See lesson location section."),
          "rationale": "Location section of organ page.",
        },
        {
          "prompt": f"State one clinical-education pearl about the {name}.",
          "answer": str(pearls[0]) if pearls else "Review clinical pearls on the organ learning page.",
          "rationale": "Clinical pearls section.",
        },
      ]
      label = "viva" if mode == "viva_questions" else "practice"
      return {
        "title": f"{name} {label} questions",
        "answer": f"Use these educational {label} questions (offline mode).",
        "questions": qs,
        "bullets": [],
        "flashcards": [],
        "mnemonics": [],
      }

    if mode in ("mnemonics",):
      mnemonic = pearls[0] if pearls else f"Link {name} to its system role using a simple story mnemonic."
      return {
        "title": f"{name} mnemonics",
        "answer": f"Memory aid (educational): {mnemonic}",
        "mnemonics": [str(mnemonic)],
        "bullets": [str(x) for x in functions[:4]],
        "flashcards": [],
        "questions": [],
      }

    bullets = [str(x) for x in (functions[:5] or objectives[:5] or pearls[:3])]
    answer_bits = [str(overview)]
    if question:
      answer_bits.append(f"Regarding your question (“{question}”), review the lesson context above and related sections.")
    if mode == "tamil":
      answer_bits.insert(0, f"{name} பற்றிய கல்வி விளக்கம் (educational overview):")
    if mode in ("one_minute_summary", "five_minute_revision", "exam_notes"):
      answer_bits.append("Key revision points are listed below.")

    return {
      "title": f"{TUTOR_MODES.get(mode, {}).get('label', 'Tutor')}: {name}",
      "answer": "\n\n".join(answer_bits),
      "bullets": bullets,
      "flashcards": [],
      "questions": [],
      "mnemonics": [],
    }

  @classmethod
  def _normalize_payload(
    cls,
    data: dict[str, Any],
    *,
    mode: str,
    provider: str,
    used_fallback: bool,
    meta: dict[str, Any],
    processing_ms: int,
  ) -> dict[str, Any]:
    answer = sanitize_educational_text(str(data.get("answer") or "").strip())
    disclaimer = ensure_short_disclaimer(
      sanitize_educational_text(str(data.get("disclaimer") or "").strip())
    )
    bullets = [
      sanitize_educational_text(str(b).strip())
      for b in (data.get("bullets") or [])
      if str(b).strip()
    ]
    mnemonics = [
      sanitize_educational_text(str(m).strip())
      for m in (data.get("mnemonics") or [])
      if str(m).strip()
    ]
    flashcards = []
    for card in data.get("flashcards") or []:
      if not isinstance(card, dict):
        continue
      front = sanitize_educational_text(str(card.get("front") or "").strip())
      back = sanitize_educational_text(str(card.get("back") or "").strip())
      if front and back:
        flashcards.append({"front": front, "back": back})
    questions = []
    for q in data.get("questions") or []:
      if not isinstance(q, dict):
        continue
      prompt = sanitize_educational_text(str(q.get("prompt") or "").strip())
      if not prompt:
        continue
      questions.append(
        {
          "prompt": prompt,
          "answer": sanitize_educational_text(str(q.get("answer") or "").strip()),
          "rationale": sanitize_educational_text(str(q.get("rationale") or "").strip()),
        }
      )

    title = sanitize_educational_text(str(data.get("title") or meta.get("title") or "AI Tutor"))
    if not answer:
      answer = "Educational tutor content is temporarily limited. Please review the organ lesson sections."

    return {
      "title": title,
      "answer": answer,
      "bullets": bullets,
      "flashcards": flashcards,
      "questions": questions,
      "mnemonics": mnemonics,
      "disclaimer": disclaimer,
      "mode": mode,
      "mode_label": TUTOR_MODES.get(mode, {}).get("label"),
      "provider": provider,
      "used_fallback": used_fallback,
      "processing_time_ms": processing_ms,
      "tutor_version": TUTOR_VERSION,
      "context": {
        "scope": meta.get("scope"),
        "organ_slug": meta.get("organ_slug"),
        "system_slug": meta.get("system_slug"),
        "title": meta.get("title"),
      },
      "modes": cls.list_modes(),
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "prescribes_medication": False,
        "note": "AI Tutor responses are for learning only and must not be used as a clinical diagnosis or treatment plan.",
      },
    }
