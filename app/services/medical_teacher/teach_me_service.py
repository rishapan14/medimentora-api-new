"""Persisted, source-grounded guided teaching sessions for uploaded lessons."""

from __future__ import annotations

import math
import re
from typing import Any

from flask import current_app

from app.extensions import db
from app.models.book_model import Book
from app.models.course_model import Lesson
from app.models.quiz_model import Question
from app.models.tutor_model import TutorMessage, TutorSession
from app.services.medical_teacher.tutor_service import TUTOR_DISCLAIMER
from app.utils import utc_now

TEACH_ME_DIFFICULTIES = {
  "beginner": {"label": "Beginner", "question_difficulty": "easy"},
  "intermediate": {"label": "Intermediate", "question_difficulty": "medium"},
  "advanced": {"label": "Advanced", "question_difficulty": "hard"},
}
TEACH_ME_VERSION = "guided-grounded-v1"
TEACH_ME_LANGUAGES = {"en": {"label": "English"}}
_DIFFICULTY_ORDER = ("beginner", "intermediate", "advanced")
_WORD_RE = re.compile(r"[A-Za-z0-9À-\uFFFF]+", re.UNICODE)
_STOP_WORDS = {
  "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it",
  "of", "on", "or", "that", "the", "this", "to", "was", "were", "with",
}


class TeachMeService:
  """Turns generated lesson content into an adaptive, step-by-step teaching flow."""

  @staticmethod
  def configuration() -> dict[str, Any]:
    return {
      "difficulties": [
        {"id": key, "label": value["label"]}
        for key, value in TEACH_ME_DIFFICULTIES.items()
      ],
      "languages": [{"id": key, "label": value["label"]} for key, value in TEACH_ME_LANGUAGES.items()],
      "grounding": {
        "source_policy": "uploaded_document_only",
        "adaptive": True,
        "educational_only": True,
      },
    }

  @classmethod
  def create_session(
    cls,
    book_id: int,
    user_id: int,
    *,
    lesson_id: int,
    difficulty: str = "beginner",
    language: str = "en",
    restart: bool = False,
  ) -> tuple[TutorSession, bool]:
    book, lesson = cls._owned_context(book_id, user_id, lesson_id)
    difficulty_key = cls._difficulty(difficulty)
    language_key = cls._language(language)
    existing = (
      TutorSession.query.filter_by(
        user_id=user_id,
        book_id=book.id,
        lesson_id=lesson.id,
        session_type="teach_me",
        status="active",
      )
      .order_by(TutorSession.updated_at.desc(), TutorSession.id.desc())
      .first()
    )
    if existing and not restart:
      return existing, True
    if existing:
      existing.status = "restarted"

    plan = cls._build_plan(book, lesson, user_id)
    if not plan:
      raise ValueError("This lesson does not contain enough grounded material for Teach Me mode.")
    session = TutorSession(
      user_id=user_id,
      book_id=book.id,
      course_id=book.generated_course.id,
      lesson_id=lesson.id,
      topic_id=lesson.topic_id,
      title=f"Teach Me: {lesson.title}"[:200],
      mode="teach_me",
      language=language_key,
      session_type="teach_me",
      difficulty=difficulty_key,
      current_step=0,
      total_steps=len(plan),
      correct_answers=0,
      incorrect_answers=0,
      plan_json=plan,
      state_json={
        "correct_streak": 0,
        "incorrect_streak": 0,
        "answered_question_ids": [],
        "version": TEACH_ME_VERSION,
      },
      status="active",
    )
    db.session.add(session)
    db.session.commit()
    return session, False

  @staticmethod
  def list_sessions(book_id: int, user_id: int, limit: int = 20) -> list[TutorSession]:
    if not Book.query.filter_by(id=book_id, user_id=user_id).first():
      raise LookupError("Book not found.")
    return (
      TutorSession.query.filter_by(book_id=book_id, user_id=user_id, session_type="teach_me")
      .order_by(TutorSession.updated_at.desc(), TutorSession.id.desc())
      .limit(max(1, min(100, int(limit or 20))))
      .all()
    )

  @staticmethod
  def get_session(book_id: int, user_id: int, public_id: str) -> TutorSession:
    session = TutorSession.query.filter_by(
      public_id=public_id,
      book_id=book_id,
      user_id=user_id,
      session_type="teach_me",
    ).first()
    if not session:
      raise LookupError("Teach Me session not found.")
    return session

  @classmethod
  def serialize(cls, session: TutorSession) -> dict[str, Any]:
    data = session.to_dict()
    total = max(0, int(session.total_steps or 0))
    current = max(0, int(session.current_step or 0))
    answered = int(session.correct_answers or 0) + int(session.incorrect_answers or 0)
    data.update({
      "progress_percent": 100 if session.status == "completed" else round((current / total) * 100) if total else 0,
      "accuracy": round((int(session.correct_answers or 0) / answered) * 100) if answered else 0,
      "current_step_data": cls._current_step(session),
      "grounding": {
        "source_policy": "uploaded_document_only",
        "based_on_uploaded_material": True,
        "note": TUTOR_DISCLAIMER,
      },
    })
    return data

  @classmethod
  def advance(cls, book_id: int, user_id: int, session_id: str) -> dict[str, Any]:
    session = cls.get_session(book_id, user_id, session_id)
    cls._require_active(session)
    current = cls._current_step(session)
    if current and current.get("type") == "question":
      raise ValueError("Answer the checkpoint before continuing.")
    cls._move_next(session)
    db.session.commit()
    return {"session": cls.serialize(session)}

  @classmethod
  def answer(cls, book_id: int, user_id: int, session_id: str, answer: str) -> dict[str, Any]:
    session = cls.get_session(book_id, user_id, session_id)
    cls._require_active(session)
    clean_answer = " ".join(str(answer or "").split())
    if not clean_answer or len(clean_answer) > 2000:
      raise ValueError("An answer between 1 and 2000 characters is required.")
    step = cls._current_step(session, include_answer=True)
    if not step or step.get("type") != "question":
      raise ValueError("The current Teach Me step is not a question.")

    correct_answer = str(step.get("correct_answer") or "").strip()
    is_correct = cls._answer_is_correct(clean_answer, correct_answer, str(step.get("question_type") or ""))
    difficulty_before = session.difficulty or "beginner"
    state = dict(session.state_json or {})
    answered_ids = list(state.get("answered_question_ids") or [])
    question_id = step.get("question_id")
    if question_id is not None and question_id not in answered_ids:
      answered_ids.append(question_id)
    state["answered_question_ids"] = answered_ids

    if is_correct:
      session.correct_answers = int(session.correct_answers or 0) + 1
      state["correct_streak"] = int(state.get("correct_streak") or 0) + 1
      state["incorrect_streak"] = 0
      if state["correct_streak"] >= 2:
        session.difficulty = cls._shift_difficulty(difficulty_before, 1)
        state["correct_streak"] = 0
    else:
      session.incorrect_answers = int(session.incorrect_answers or 0) + 1
      state["incorrect_streak"] = int(state.get("incorrect_streak") or 0) + 1
      state["correct_streak"] = 0
      if state["incorrect_streak"] >= 2:
        session.difficulty = cls._shift_difficulty(difficulty_before, -1)
        state["incorrect_streak"] = 0
    session.state_json = state

    explanation = str(step.get("explanation") or "").strip()
    feedback_text = (
      f"Correct. {explanation}" if is_correct
      else f"Not quite. The expected answer is: {correct_answer}. {explanation}"
    ).strip()
    evaluation = {
      "correct": is_correct,
      "message": feedback_text,
      "correct_answer": correct_answer,
      "explanation": explanation,
      "difficulty_before": difficulty_before,
      "difficulty_after": session.difficulty or difficulty_before,
      "source": step.get("source"),
    }
    user_message = TutorMessage(
        session_id=session.id,
        role="user",
        content=clean_answer,
        mode="teach_me",
        language=session.language,
        metadata_json={"step_id": step.get("id"), "question_id": question_id},
      )
    assistant_message = TutorMessage(
        session_id=session.id,
        role="assistant",
        content=feedback_text,
        mode="teach_me",
        language=session.language,
        provider="deterministic_grounded",
        source_json=[step.get("source")] if step.get("source") else [],
        metadata_json={
          "supported": True,
          "used_fallback": False,
          "step_id": step.get("id"),
          "question_id": question_id,
          "correct": is_correct,
          "difficulty_before": difficulty_before,
          "difficulty_after": session.difficulty,
          "safety": {
            "educational_only": True,
            "not_a_diagnosis": True,
            "prescribes_medication": False,
            "note": TUTOR_DISCLAIMER,
          },
        },
      )
    db.session.add_all([user_message, assistant_message])
    cls._move_next(session)
    db.session.commit()
    try:
      from app.services.medical_teacher.adaptive_learning_service import AdaptiveLearningService
      AdaptiveLearningService.refresh_book(book_id, user_id)
    except Exception:
      current_app.logger.exception("Adaptive topic mastery refresh failed after Teach Me answer.")
    try:
      from app.services.learning_dashboard_service import LearningDashboardService
      LearningDashboardService.record_activity(
        user_id,
        "teach_me",
        str(assistant_message.id),
        session.title or "Teach Me session",
        book_id=session.book_id,
        course_id=session.course_id,
        topic_id=session.topic_id,
        lesson_id=session.lesson_id,
        metadata={"correct": is_correct, "difficulty": session.difficulty},
        occurred_at=assistant_message.created_at,
      )
    except Exception:
      current_app.logger.exception("Learning activity recording failed after Teach Me answer.")
    return {"session": cls.serialize(session), "evaluation": evaluation}

  @classmethod
  def _build_plan(cls, book: Book, lesson: Lesson, user_id: int) -> list[dict[str, Any]]:
    content = lesson.content_json or {}
    lesson_source = cls._lesson_source(book, lesson)
    overview = cls._clean_text(content.get("overview") or lesson.summary or lesson.content)
    detailed = cls._clean_text(content.get("detailed_explanation") or lesson.content)
    concepts = cls._string_list(content.get("key_concepts") or content.get("key_points"))
    definitions = content.get("important_definitions") if isinstance(content.get("important_definitions"), list) else []
    revision = cls._string_list(content.get("quick_revision") or content.get("key_points"))

    plan: list[dict[str, Any]] = []
    if overview:
      plan.append(cls._lesson_step("introduction", "Start with the big picture", overview, lesson_source))
    if concepts:
      plan.append(cls._lesson_step(
        "concepts", "Build the core concepts", "\n".join(f"• {item}" for item in concepts[:6]), lesson_source,
      ))
    elif definitions:
      lines = [
        f"• {item.get('term')}: {item.get('definition')}"
        for item in definitions[:6]
        if isinstance(item, dict) and item.get("term") and item.get("definition")
      ]
      if lines:
        plan.append(cls._lesson_step("concepts", "Learn the key definitions", "\n".join(lines), lesson_source))

    candidates = cls._question_candidates(book.id, lesson, user_id)
    if candidates:
      plan.append({"id": "checkpoint-1", "type": "question", "title": "Check your understanding", "candidates": candidates})
    else:
      fallback_answer = concepts[0] if concepts else overview
      if fallback_answer:
        plan.append({
          "id": "checkpoint-1",
          "type": "question",
          "title": "Check your understanding",
          "candidates": [{
            "question_id": "lesson-fallback-1",
            "question_text": f"In your own words, explain one important idea from {lesson.title}.",
            "question_type": "short_answer",
            "difficulty": "easy",
            "options": [],
            "correct_answer": fallback_answer,
            "explanation": fallback_answer,
            "source": lesson_source,
          }],
        })
    if detailed and detailed != overview:
      plan.append(cls._lesson_step("explanation", "Connect the ideas", detailed, lesson_source))
    if len(candidates) > 1:
      plan.append({"id": "checkpoint-2", "type": "question", "title": "Apply what you learned", "candidates": candidates})
    summary_items = revision or concepts
    summary = "\n".join(f"• {item}" for item in summary_items[:8]) if summary_items else overview
    if summary:
      plan.append(cls._lesson_step("summary", "Lock in the lesson", summary, lesson_source))
    for index, step in enumerate(plan, start=1):
      step["position"] = index
    return plan

  @staticmethod
  def _lesson_step(step_id: str, title: str, content: str, source: dict[str, Any]) -> dict[str, Any]:
    step_type = "summary" if step_id == "summary" else "explanation"
    return {"id": step_id, "type": step_type, "title": title, "content": content, "source": source}

  @staticmethod
  def _question_candidates(book_id: int, lesson: Lesson, user_id: int) -> list[dict[str, Any]]:
    rows = (
      Question.query.filter_by(book_id=book_id, course_id=lesson.course_id, lesson_id=lesson.id, user_id=user_id)
      .order_by(Question.priority_score.desc(), Question.order_index, Question.id)
      .limit(30)
      .all()
    )
    return [{
      "question_id": row.id,
      "question_text": row.question_text,
      "question_type": row.question_type or "short_answer",
      "difficulty": row.difficulty or "medium",
      "options": row.options or [],
      "correct_answer": row.correct_answer,
      "explanation": row.explanation or row.correct_answer,
      "source": row.source_json or {},
    } for row in rows]

  @classmethod
  def _current_step(cls, session: TutorSession, include_answer: bool = False) -> dict[str, Any] | None:
    plan = list(session.plan_json or [])
    index = int(session.current_step or 0)
    if session.status == "completed" or index < 0 or index >= len(plan):
      return None
    step = dict(plan[index])
    if step.get("type") == "question":
      candidates = list(step.pop("candidates", []) or [])
      answered = set((session.state_json or {}).get("answered_question_ids") or [])
      desired = TEACH_ME_DIFFICULTIES.get(session.difficulty or "beginner", {}).get("question_difficulty", "easy")
      available = [item for item in candidates if item.get("question_id") not in answered]
      chosen = next((item for item in available if item.get("difficulty") == desired), None)
      chosen = chosen or (available[0] if available else (candidates[0] if candidates else None))
      if chosen:
        step.update(chosen)
      if not include_answer:
        step.pop("correct_answer", None)
        step.pop("explanation", None)
    step["position"] = index + 1
    step["total_steps"] = len(plan)
    return step

  @staticmethod
  def _answer_is_correct(answer: str, correct_answer: str, question_type: str) -> bool:
    actual = TeachMeService._normalize(answer)
    expected = TeachMeService._normalize(correct_answer)
    if not actual or not expected:
      return False
    if actual == expected:
      return True
    if question_type in {"multiple_choice", "true_false", "fill_in_blank"}:
      return expected in actual or actual in expected
    expected_terms = TeachMeService._meaningful_terms(expected)
    actual_terms = TeachMeService._meaningful_terms(actual)
    if not expected_terms:
      return False
    required = max(1, math.ceil(len(expected_terms) * 0.45))
    return len(expected_terms & actual_terms) >= required

  @staticmethod
  def _normalize(value: str) -> str:
    return " ".join(_WORD_RE.findall(str(value or "").casefold()))

  @staticmethod
  def _meaningful_terms(value: str) -> set[str]:
    return {item for item in _WORD_RE.findall(value.casefold()) if len(item) > 2 and item not in _STOP_WORDS}

  @staticmethod
  def _shift_difficulty(value: str, amount: int) -> str:
    try:
      index = _DIFFICULTY_ORDER.index(value)
    except ValueError:
      index = 0
    return _DIFFICULTY_ORDER[max(0, min(len(_DIFFICULTY_ORDER) - 1, index + amount))]

  @staticmethod
  def _move_next(session: TutorSession) -> None:
    session.current_step = int(session.current_step or 0) + 1
    session.updated_at = utc_now()
    if session.current_step >= int(session.total_steps or 0):
      session.status = "completed"
      session.completed_at = utc_now()

  @staticmethod
  def _require_active(session: TutorSession) -> None:
    if session.status != "active":
      raise ValueError("This Teach Me session is already complete.")

  @staticmethod
  def _owned_context(book_id: int, user_id: int, lesson_id: int) -> tuple[Book, Lesson]:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    if book.rag_status != "ready" or not book.generated_course:
      raise ValueError("Document index is not ready for Teach Me mode.")
    lesson = Lesson.query.filter_by(id=lesson_id, course_id=book.generated_course.id).first()
    if not lesson:
      raise LookupError("Lesson not found.")
    return book, lesson

  @staticmethod
  def _difficulty(value: str) -> str:
    key = str(value or "").strip().lower()
    if key not in TEACH_ME_DIFFICULTIES:
      raise ValueError("Unsupported Teach Me difficulty.")
    return key

  @staticmethod
  def _language(value: str) -> str:
    aliases = {"english": "en"}
    key = aliases.get(str(value or "").strip().lower(), str(value or "").strip().lower())
    if key not in TEACH_ME_LANGUAGES:
      raise ValueError("Unsupported Teach Me language.")
    return key

  @staticmethod
  def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())[:6000]

  @staticmethod
  def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
      return []
    return [" ".join(str(item).split()) for item in value if str(item).strip()]

  @staticmethod
  def _lesson_source(book: Book, lesson: Lesson) -> dict[str, Any]:
    content = lesson.content_json or {}
    references = content.get("source_references") if isinstance(content, dict) else None
    source = dict(references[0]) if isinstance(references, list) and references and isinstance(references[0], dict) else dict(lesson.source_json or {})
    source.setdefault("source_kind", "uploaded_document")
    source.setdefault("document_id", book.id)
    source.setdefault("document_title", book.title)
    source.setdefault("course_id", lesson.course_id)
    source.setdefault("topic_id", lesson.topic_id)
    source.setdefault("topic_title", lesson.title)
    source.setdefault("lesson_id", lesson.id)
    source.setdefault("page_numbers", [])
    return source
