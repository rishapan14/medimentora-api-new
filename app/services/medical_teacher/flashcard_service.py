"""Source-grounded flashcards and spaced-repetition review for uploaded courses."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models.body_system_model import HubFlashcard, HubFlashcardFavorite
from app.models.book_model import Book
from app.models.quiz_model import Question, Quiz
from app.utils import utc_now

FLASHCARD_STYLES = ("easy", "medium", "hard", "exam", "nursing", "clinical")
REVIEW_ACTIONS = ("correct", "incorrect", "review_later", "mastered")


@dataclass(frozen=True)
class FlashcardGenerationResult:
  book: Book
  cards: list[HubFlashcard]
  created_count: int
  reused_count: int

  def to_dict(self, user_id: int):
    payload = LearningFlashcardService.serialize_cards(self.cards, user_id)
    return {
      "book_id": self.book.id,
      "course_id": self.book.generated_course.id if self.book.generated_course else None,
      "created_count": self.created_count,
      "reused_count": self.reused_count,
      "card_count": len(self.cards),
      **payload,
      "styles": list(FLASHCARD_STYLES),
      "grounding": {
        "source_policy": "uploaded_document_only",
        "note": "Card answers and explanations retain the source question's page and chunk references.",
      },
    }


class LearningFlashcardService:
  @classmethod
  def generate_for_book(
    cls,
    book_id: int,
    user_id: int,
    *,
    styles: list[str] | None = None,
    force: bool = False,
  ) -> FlashcardGenerationResult:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    course = book.generated_course
    if not course or course.question_generation_status != "ready":
      raise ValueError("Source-grounded questions must be ready before flashcard generation.")
    selected_styles = cls._styles(styles)
    bank = Quiz.query.filter_by(source_book_id=book.id, quiz_type="question_bank").first()
    questions = (
      bank.questions.order_by(Question.priority_score.desc(), Question.order_index).all()
      if bank else []
    )
    signature = cls._signature(book, questions, selected_styles)
    existing = (
      HubFlashcard.query.filter_by(
        book_id=book.id,
        owner_user_id=user_id,
        origin="uploaded_document",
      )
      .order_by(HubFlashcard.id)
      .all()
    )
    if existing and not force:
      return FlashcardGenerationResult(book, existing, 0, len(existing))

    course.flashcard_generation_status = "generating"
    db.session.flush()
    try:
      if existing:
        existing_ids = [card.id for card in existing]
        HubFlashcardFavorite.query.filter(
          HubFlashcardFavorite.flashcard_id.in_(existing_ids)
        ).delete(synchronize_session=False)
        for card in existing:
          db.session.delete(card)
        db.session.flush()
      specs = cls._specs(questions, selected_styles)
      cards = []
      for spec in specs:
        question = spec["question"]
        source = dict(question.source_json or {})
        source["source_question_id"] = question.id
        card = HubFlashcard(
          lesson_id=question.lesson_id,
          owner_user_id=user_id,
          book_id=book.id,
          course_id=course.id,
          module_id=question.module_id,
          topic_id=question.topic_id,
          front_text=spec["front"][:4000],
          back_text=spec["back"][:8000],
          card_level=spec["style"],
          topic_tags=[spec["style"], question.question_type, question.priority_level],
          source_json=source,
          source_hash=question.source_hash,
          generation_hash=signature,
          origin="uploaded_document",
          generation_method="grounded_question_conversion",
          generated_at=utc_now(),
          is_published=False,
          created_by=user_id,
        )
        db.session.add(card)
        cards.append(card)
      course.flashcard_generation_status = "ready"
      db.session.commit()
      return FlashcardGenerationResult(book, cards, len(cards), 0)
    except Exception:
      db.session.rollback()
      failed = book.generated_course
      if failed:
        failed.flashcard_generation_status = "failed"
        db.session.commit()
      raise

  @classmethod
  def list_owned(
    cls,
    book_id: int,
    user_id: int,
    *,
    style: str | None = None,
    lesson_id: int | None = None,
    status: str | None = None,
    due_only: bool = False,
  ) -> dict:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    query = HubFlashcard.query.filter_by(
      book_id=book.id,
      owner_user_id=user_id,
      origin="uploaded_document",
    )
    if style:
      normalized = str(style).strip().lower()
      if normalized not in FLASHCARD_STYLES:
        raise ValueError("Unsupported flashcard style.")
      query = query.filter_by(card_level=normalized)
    if lesson_id is not None:
      query = query.filter_by(lesson_id=lesson_id)
    cards = query.order_by(HubFlashcard.topic_id, HubFlashcard.id).all()
    review_map = cls._review_map(cards, user_id)
    now = utc_now()
    if status:
      cards = [card for card in cards if (review_map.get(card.id).status if review_map.get(card.id) else "new") == status]
    if due_only:
      cards = [
        card for card in cards
        if not review_map.get(card.id)
        or (
          review_map[card.id].status != "mastered"
          and (review_map[card.id].next_review_at is None or review_map[card.id].next_review_at <= now)
        )
      ]
    return {
      "book_id": book.id,
      "course_id": book.generated_course.id if book.generated_course else None,
      **cls.serialize_cards(cards, user_id),
      "styles": list(FLASHCARD_STYLES),
      "review_actions": list(REVIEW_ACTIONS),
      "spaced_repetition": {
        "available": True,
        "algorithm": "SM-2-inspired",
        "note": "Scheduling adapts interval and ease from each review action.",
      },
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def review(cls, book_id: int, user_id: int, card_id: int, action: str) -> dict:
    card = HubFlashcard.query.filter_by(
      id=card_id,
      book_id=book_id,
      owner_user_id=user_id,
      origin="uploaded_document",
    ).first()
    if not card:
      raise LookupError("Flashcard not found.")
    rating = str(action or "").strip().lower()
    if rating not in REVIEW_ACTIONS:
      raise ValueError("Review action must be correct, incorrect, review_later, or mastered.")
    review = HubFlashcardFavorite.query.filter_by(user_id=user_id, flashcard_id=card.id).first()
    if not review:
      review = HubFlashcardFavorite(
        user_id=user_id,
        flashcard_id=card.id,
        ease_factor=2.5,
        interval_days=0,
        repetitions=0,
        status="learning",
      )
      db.session.add(review)
    now = utc_now()
    ease = float(review.ease_factor or 2.5)
    repetitions = int(review.repetitions or 0)
    interval = int(review.interval_days or 0)
    if rating == "correct":
      repetitions += 1
      interval = 1 if repetitions == 1 else 6 if repetitions == 2 else max(7, round(interval * ease))
      ease = min(3.0, ease + 0.1)
      review.correct_count = int(review.correct_count or 0) + 1
      review.status = "learning"
    elif rating == "incorrect":
      repetitions = 0
      interval = 1
      ease = max(1.3, ease - 0.2)
      review.incorrect_count = int(review.incorrect_count or 0) + 1
      review.status = "learning"
    elif rating == "review_later":
      interval = 1
      review.status = "review_later"
    else:
      repetitions = max(3, repetitions + 1)
      interval = max(30, interval)
      review.correct_count = int(review.correct_count or 0) + 1
      review.status = "mastered"
    review.ease_factor = ease
    review.repetitions = repetitions
    review.interval_days = interval
    review.review_count = int(review.review_count or 0) + 1
    review.last_rating = rating
    review.last_reviewed_at = now
    review.next_review_at = now + timedelta(days=interval)
    db.session.commit()
    try:
      from app.services.medical_teacher.adaptive_learning_service import AdaptiveLearningService
      AdaptiveLearningService.refresh_book(book_id, user_id)
    except Exception:
      current_app.logger.exception("Adaptive topic mastery refresh failed after flashcard review.")
    try:
      from app.services.learning_dashboard_service import LearningDashboardService
      LearningDashboardService.record_activity(
        user_id,
        "flashcard_review",
        f"{review.id}:{review.review_count or 0}",
        f"Reviewed flashcard: {card.front_text[:160]}",
        book_id=card.book_id,
        course_id=card.course_id,
        module_id=card.module_id,
        topic_id=card.topic_id,
        lesson_id=card.lesson_id,
        metadata={"rating": rating},
        occurred_at=review.last_reviewed_at,
      )
    except Exception:
      current_app.logger.exception("Learning activity recording failed after flashcard review.")
    return {
      "card": card.to_dict(),
      "review": review.to_dict(),
      "message": cls._review_message(rating, interval),
    }

  @classmethod
  def serialize_cards(cls, cards: list[HubFlashcard], user_id: int) -> dict:
    review_map = cls._review_map(cards, user_id)
    items = []
    for card in cards:
      data = card.to_dict()
      review = review_map.get(card.id)
      data["review"] = review.to_dict() if review else {
        "status": "new",
        "correct_count": 0,
        "incorrect_count": 0,
        "review_count": 0,
        "next_review_at": None,
      }
      items.append(data)
    all_reviews = list(review_map.values())
    correct = sum(int(item.correct_count or 0) for item in all_reviews)
    incorrect = sum(int(item.incorrect_count or 0) for item in all_reviews)
    due = sum(
      1 for card in cards
      if not review_map.get(card.id)
      or (
        review_map[card.id].status != "mastered"
        and (review_map[card.id].next_review_at is None or review_map[card.id].next_review_at <= utc_now())
      )
    )
    return {
      "cards": items,
      "total": len(cards),
      "stats": {
        "due": due,
        "new": sum(1 for card in cards if card.id not in review_map),
        "learning": sum(1 for item in all_reviews if item.status in ("learning", "review_later", None)),
        "mastered": sum(1 for item in all_reviews if item.status == "mastered"),
        "accuracy": round(correct / (correct + incorrect) * 100, 2) if correct + incorrect else 0,
      },
    }

  @staticmethod
  def _review_map(cards: list[HubFlashcard], user_id: int) -> dict[int, HubFlashcardFavorite]:
    ids = [card.id for card in cards if card.id is not None]
    if not ids:
      return {}
    return {
      item.flashcard_id: item
      for item in HubFlashcardFavorite.query.filter(
        HubFlashcardFavorite.user_id == user_id,
        HubFlashcardFavorite.flashcard_id.in_(ids),
      ).all()
    }

  @classmethod
  def _styles(cls, styles: list[str] | None) -> list[str]:
    if styles is None:
      configured = str(current_app.config.get("TEACHER_FLASHCARD_STYLES") or "").split(",")
      styles = configured
    normalized = list(dict.fromkeys(str(item).strip().lower() for item in styles if str(item).strip()))
    invalid = [item for item in normalized if item not in FLASHCARD_STYLES]
    if invalid:
      raise ValueError(f"Unsupported flashcard style: {invalid[0]}.")
    return normalized or list(FLASHCARD_STYLES)

  @classmethod
  def _specs(cls, questions: list[Question], styles: list[str]) -> list[dict]:
    specs = []
    seen = set()
    for question in questions:
      base_style = question.difficulty if question.difficulty in ("easy", "medium", "hard") else "medium"
      candidates = []
      if base_style in styles:
        candidates.append((base_style, question.question_text))
      evidence = " ".join((question.explanation or "").split())
      combined = f"{question.question_text} {evidence}"
      if "exam" in styles and question.priority_level in ("high", "important"):
        candidates.append(("exam", f"Exam revision: {question.question_text}"))
      if "clinical" in styles and (
        question.question_type == "case_based" or re.search(r"\b(clinical|patient|symptom|case)\b", combined, re.I)
      ):
        candidates.append(("clinical", f"Clinical revision: {question.question_text}"))
      if "nursing" in styles and re.search(r"\b(nurs|patient care|assessment|monitoring)\w*\b", combined, re.I):
        candidates.append(("nursing", f"Nursing revision: {question.question_text}"))
      back = question.correct_answer
      if evidence and cls._normalize(evidence) != cls._normalize(back):
        back = f"{back}\n\nSource explanation: {evidence}"
      for style, front in candidates:
        key = (style, cls._normalize(front), cls._normalize(back))
        if key in seen:
          continue
        seen.add(key)
        specs.append({"question": question, "front": front, "back": back, "style": style})
    return specs

  @staticmethod
  def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())

  @staticmethod
  def _signature(book: Book, questions: list[Question], styles: list[str]) -> str:
    payload = {
      "document_hash": book.content_hash,
      "questions": [(item.id, item.source_hash) for item in questions],
      "styles": sorted(styles),
      "version": "phase10-v1",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

  @staticmethod
  def _review_message(action: str, interval: int) -> str:
    if action == "mastered":
      return "Marked mastered. Scheduled for a long-term review."
    if action == "incorrect":
      return "Added to tomorrow's review so you can reinforce it."
    if action == "review_later":
      return "Saved for another review."
    return f"Correct. Next review is scheduled in {interval} day(s)."
