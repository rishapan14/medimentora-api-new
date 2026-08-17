"""Hub quiz generation & listing (Phase 7).

Reuses LMS Quiz / Question models + BodySystemQuiz links.
Generates educational assessments from organ/system lesson content.
"""

from __future__ import annotations

import logging
from typing import Any

from app.extensions import db
from app.models.body_system_model import BodySystem, BodySystemProgress, BodySystemQuiz, Organ
from app.models.quiz_model import Question, Quiz, Result
from app.services.body_systems.hub_service import BodySystemHubService
from app.utils import utc_now

logger = logging.getLogger(__name__)

HUB_QUIZ_PREFIX = "[Hub]"
DIFFICULTY_MAP = {
  "beginner": "easy",
  "easy": "easy",
  "intermediate": "medium",
  "medium": "medium",
  "advanced": "hard",
  "hard": "hard",
}


class HubQuizService:
  """Generate and list body-system quizzes via the existing LMS."""

  @classmethod
  def list_system_quizzes(
    cls, system_slug: str, *, user_id: int | None = None
  ) -> dict[str, Any] | None:
    system = BodySystemHubService._resolve_system(system_slug)
    if not system:
      return None
    links = (
      BodySystemQuiz.query.filter_by(body_system_id=system.id)
      .order_by(BodySystemQuiz.sort_order, BodySystemQuiz.id)
      .all()
    )
    items = []
    for link in links:
      quiz = Quiz.query.get(link.quiz_id)
      if not quiz or not quiz.is_published:
        continue
      row = {**link.to_dict(), "quiz": quiz.to_dict(include_questions=False)}
      if user_id:
        best = (
          Result.query.filter_by(user_id=user_id, quiz_id=quiz.id)
          .order_by(Result.score.desc())
          .first()
        )
        row["best_score"] = float(best.score) if best else None
        row["attempts"] = Result.query.filter_by(user_id=user_id, quiz_id=quiz.id).count()
        row["passed"] = bool(best and best.passed) if best else False
      items.append(row)
    return {
      "body_system": system.to_dict(include_counts=False),
      "items": items,
      "total": len(items),
      "supported_question_types": [
        "multiple_choice",
        "true_false",
        "fill_in_blank",
        "case_based",
        "image_based",
      ],
      "drag_drop": {"available": False, "note": "Future question type"},
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "Hub quizzes are educational assessments only.",
      },
    }

  @classmethod
  def generate_system_quiz(
    cls,
    system_slug: str,
    *,
    user_id: int | None = None,
    difficulty: str | None = None,
    organ_slug: str | None = None,
    force: bool = False,
  ) -> tuple[dict[str, Any] | None, str]:
    system = BodySystemHubService._resolve_system(system_slug)
    if not system:
      return None, "not_found"

    title = f"{HUB_QUIZ_PREFIX} {system.name} Knowledge Check"
    if organ_slug:
      organ = Organ.query.filter_by(body_system_id=system.id, slug=organ_slug.strip()).first()
      if not organ:
        return None, "not_found"
      title = f"{HUB_QUIZ_PREFIX} {organ.name} — {system.name}"

    existing = Quiz.query.filter_by(title=title).first()
    if existing and not force and existing.questions.count() > 0:
      link = BodySystemQuiz.query.filter_by(
        body_system_id=system.id, quiz_id=existing.id
      ).first()
      if not link:
        link = cls._link(system.id, existing.id)
      payload = cls._quiz_payload(link, existing, user_id=user_id)
      payload["generated"] = False
      return payload, "ok"

    organ = None
    if organ_slug:
      organ = Organ.query.filter_by(body_system_id=system.id, slug=organ_slug.strip()).first()

    specs = cls._build_question_specs(system, organ)
    if not specs:
      return None, "validation_error"

    diff = DIFFICULTY_MAP.get((difficulty or system.difficulty or "intermediate").lower(), "medium")
    if existing:
      quiz = existing
      quiz.description = cls._description(system, organ)
      quiz.difficulty = diff
      quiz.speciality = system.name
      quiz.is_published = True
      quiz.updated_at = utc_now()
      Question.query.filter_by(quiz_id=quiz.id).delete()
    else:
      quiz = Quiz(
        title=title,
        description=cls._description(system, organ),
        difficulty=diff,
        speciality=system.name,
        time_limit_minutes=20,
        is_published=True,
        quiz_type="general",
        passing_score=70,
        created_by=user_id,
      )
      db.session.add(quiz)
      db.session.flush()

    for idx, spec in enumerate(specs):
      db.session.add(
        Question(
          quiz_id=quiz.id,
          question_text=spec["question_text"],
          question_type=spec["question_type"],
          options=spec["options"],
          correct_answer=spec["correct_answer"],
          explanation=spec.get("explanation"),
          image_url=spec.get("image_url"),
          points=int(spec.get("points") or 1),
          order_index=idx,
        )
      )

    link = BodySystemQuiz.query.filter_by(body_system_id=system.id, quiz_id=quiz.id).first()
    if not link:
      link = cls._link(system.id, quiz.id)

    db.session.commit()
    payload = cls._quiz_payload(link, quiz, user_id=user_id)
    payload["generated"] = True
    return payload, "ok"

  @classmethod
  def record_progress_for_quiz(cls, user_id: int, quiz_id: int, score: float) -> None:
    """Bump BodySystemProgress when a linked hub quiz is submitted."""
    links = BodySystemQuiz.query.filter_by(quiz_id=quiz_id).all()
    if not links:
      return
    for link in links:
      progress = BodySystemProgress.query.filter_by(
        user_id=user_id, body_system_id=link.body_system_id
      ).first()
      if not progress:
        progress = BodySystemProgress(
          user_id=user_id,
          body_system_id=link.body_system_id,
          status="in_progress",
          progress_percent=0,
          started_at=utc_now(),
        )
        db.session.add(progress)
      if progress.status == "not_started":
        progress.status = "in_progress"
        progress.started_at = progress.started_at or utc_now()
      # Educational bump: quiz contribution capped
      bump = 8.0 if score >= 70 else 3.0
      progress.progress_percent = min(100.0, float(progress.progress_percent or 0) + bump)
      if progress.progress_percent >= 100:
        progress.status = "completed"
        progress.completed_at = utc_now()
      progress.updated_at = utc_now()
    db.session.commit()

    for link in links:
      progress = BodySystemProgress.query.filter_by(
        user_id=user_id, body_system_id=link.body_system_id
      ).first()
      if progress and (progress.status == "completed" or float(progress.progress_percent or 0) >= 100):
        try:
          from app.services.body_systems.hub_certificate_service import HubCertificateService

          HubCertificateService.maybe_issue_for_progress(progress)
        except Exception:
          pass

  @classmethod
  def _link(cls, body_system_id: int, quiz_id: int) -> BodySystemQuiz:
    link = BodySystemQuiz(
      body_system_id=body_system_id,
      quiz_id=quiz_id,
      is_required=False,
      sort_order=0,
    )
    db.session.add(link)
    db.session.flush()
    return link

  @classmethod
  def _quiz_payload(
    cls, link: BodySystemQuiz, quiz: Quiz, *, user_id: int | None
  ) -> dict[str, Any]:
    data = {**link.to_dict(), "quiz": quiz.to_dict(include_questions=True)}
    if user_id:
      best = (
        Result.query.filter_by(user_id=user_id, quiz_id=quiz.id)
        .order_by(Result.score.desc())
        .first()
      )
      data["best_score"] = float(best.score) if best else None
      data["attempts"] = Result.query.filter_by(user_id=user_id, quiz_id=quiz.id).count()
    data["safety"] = {"educational_only": True, "not_a_diagnosis": True}
    return data

  @staticmethod
  def _description(system: BodySystem, organ: Organ | None) -> str:
    focus = organ.name if organ else system.name
    return (
      f"Educational hub quiz for {focus}. "
      "For learning only — not a clinical diagnosis tool. "
      "Supports MCQ, true/false, fill-in-the-blank, case-based, and image-identification style questions."
    )

  @classmethod
  def _build_question_specs(
    cls, system: BodySystem, organ: Organ | None
  ) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if organ:
      specs.extend(cls._specs_from_organ(organ, system))
    else:
      # Prefer first published organs for variety
      organs = (
        Organ.query.filter_by(body_system_id=system.id, is_active=True)
        .order_by(Organ.sort_order, Organ.name)
        .limit(4)
        .all()
      )
      if organs:
        for o in organs:
          specs.extend(cls._specs_from_organ(o, system)[:3])
      else:
        specs.extend(cls._specs_from_system_only(system))

    # Cap to a focused quiz length
    return specs[:12]

  @classmethod
  def _specs_from_organ(cls, organ: Organ, system: BodySystem) -> list[dict[str, Any]]:
    cj = organ.content_json if isinstance(organ.content_json, dict) else {}
    functions = [str(f) for f in (cj.get("functions") or []) if str(f).strip()]
    parts = [str(p) for p in (cj.get("parts") or []) if str(p).strip()]
    location = str(cj.get("location_detail") or organ.location or "").strip()
    overview = str(cj.get("overview") or organ.overview or organ.short_description or "").strip()
    pearls = [str(p) for p in (cj.get("clinical_pearls") or []) if str(p).strip()]
    diseases = cj.get("common_diseases") if isinstance(cj.get("common_diseases"), list) else []

    specs: list[dict[str, Any]] = []

    # MCQ — primary function
    if functions:
      correct = functions[0]
      distractors = [
        f"Produces digestive enzymes exclusively for {system.name}",
        f"Stores bile for the {system.name}",
        f"Filters lymph only in the {system.name}",
      ]
      options = cls._unique_options(correct, distractors)
      specs.append(
        {
          "question_type": "multiple_choice",
          "question_text": f"Which option best matches an educational function of the {organ.name}?",
          "options": options,
          "correct_answer": correct,
          "explanation": f"Lesson function for {organ.name}: {correct}",
          "points": 1,
        }
      )

    # True/False — system membership
    specs.append(
      {
        "question_type": "true_false",
        "question_text": (
          f"True or False: The {organ.name} is studied as part of the {system.name} "
          "in MediMentora’s educational Body Systems Hub."
        ),
        "options": ["True", "False"],
        "correct_answer": "True",
        "explanation": f"{organ.name} is linked to the {system.name} learning path.",
        "points": 1,
      }
    )

    # Fill in the blank — location / name
    if location:
      # Use a short token from location for blank when possible
      blank_answer = organ.location.replace("_", " ") if organ.location else location.split(",")[0].strip()
      specs.append(
        {
          "question_type": "fill_in_blank",
          "question_text": (
            f"Fill in the blank (educational anatomy): The {organ.name} is primarily associated "
            f"with the body region/location known as ______."
          ),
          "options": [],
          "correct_answer": blank_answer,
          "explanation": f"Location context: {location}",
          "points": 1,
        }
      )
    else:
      specs.append(
        {
          "question_type": "fill_in_blank",
          "question_text": f"Fill in the blank: The organ slug/region key for this lesson is ______.",
          "options": [],
          "correct_answer": organ.slug,
          "explanation": f"Region key / slug: {organ.region_key or organ.slug}",
          "points": 1,
        }
      )

    # Case-based
    disease_name = None
    if diseases and isinstance(diseases[0], dict):
      disease_name = diseases[0].get("name")
    stem = overview[:280] if overview else f"A learner is reviewing educational content about the {organ.name}."
    specs.append(
      {
        "question_type": "case_based",
        "question_text": (
          f"Educational case: {stem}\n\n"
          f"Which learning focus is most appropriate for this organ lesson?"
        ),
        "options": cls._unique_options(
          f"Review anatomy, physiology, and educational clinical themes of the {organ.name}",
          [
            "Issue a definitive personal diagnosis for a real patient",
            "Prescribe medication doses without a clinician",
            "Ignore nursing assessment priorities entirely",
          ],
        ),
        "correct_answer": (
          f"Review anatomy, physiology, and educational clinical themes of the {organ.name}"
        ),
        "explanation": (
          f"Hub cases are educational. "
          + (f"Related learning topic example: {disease_name}." if disease_name else "")
        ),
        "points": 2,
      }
    )

    # Image identification style (text-described; optional illustration_url)
    if parts:
      correct_part = parts[0]
      specs.append(
        {
          "question_type": "image_based",
          "question_text": (
            f"Image identification (educational): On a labeled diagram of the {organ.name}, "
            f"which structure is a primary part learners should identify?"
          ),
          "options": cls._unique_options(
            correct_part,
            parts[1:4] + [f"Unrelated valve of the {system.name}", "Skin epidermis only"],
          ),
          "correct_answer": correct_part,
          "explanation": f"{correct_part} is listed among parts of the {organ.name}.",
          "image_url": organ.illustration_url,
          "points": 1,
        }
      )

    if pearls:
      specs.append(
        {
          "question_type": "true_false",
          "question_text": (
            f"True or False (educational pearl): \"{pearls[0]}\" is presented as a learning pearl "
            f"for the {organ.name}."
          ),
          "options": ["True", "False"],
          "correct_answer": "True",
          "explanation": "Pulled from the organ lesson clinical pearls section.",
          "points": 1,
        }
      )

    return specs

  @classmethod
  def _specs_from_system_only(cls, system: BodySystem) -> list[dict[str, Any]]:
    return [
      {
        "question_type": "multiple_choice",
        "question_text": f"What is the educational focus of the {system.name} learning path?",
        "options": cls._unique_options(
          system.short_description or system.name,
          [
            "Personal diagnosis of any patient symptom",
            "Prescribing antibiotics automatically",
            "Replacing licensed clinical care",
          ],
        ),
        "correct_answer": system.short_description or system.name,
        "explanation": "Body system short description from the Learning Hub.",
        "points": 1,
      },
      {
        "question_type": "true_false",
        "question_text": f"True or False: Hub content for the {system.name} is educational only.",
        "options": ["True", "False"],
        "correct_answer": "True",
        "explanation": "All hub materials are educational and not diagnostic.",
        "points": 1,
      },
      {
        "question_type": "fill_in_blank",
        "question_text": "Fill in the blank: The body system slug is ______.",
        "options": [],
        "correct_answer": system.slug,
        "explanation": f"Slug: {system.slug}",
        "points": 1,
      },
    ]

  @staticmethod
  def _unique_options(correct: str, distractors: list[str]) -> list[str]:
    opts: list[str] = []
    seen: set[str] = set()
    for item in [correct, *distractors]:
      text = str(item).strip()
      key = text.lower()
      if not text or key in seen:
        continue
      seen.add(key)
      opts.append(text)
      if len(opts) >= 4:
        break
    while len(opts) < 4:
      filler = f"Educational distractor {len(opts)}"
      if filler.lower() not in seen:
        opts.append(filler)
        seen.add(filler.lower())
    # Keep correct present
    if correct not in opts:
      opts[0] = correct
    return opts
