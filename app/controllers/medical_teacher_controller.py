"""HTTP controllers for AI Medical Teacher — Modules 1–2."""

from flask import current_app, request
from flask_jwt_extended import current_user

from app.helpers.response import error_response, success_response
from app.models.book_model import Chapter
from app.services.medical_teacher.book_parser import BookParser
from app.services.medical_teacher.document_service import DocumentService
from app.services.medical_teacher.document_structure_service import DocumentStructureService
from app.services.medical_teacher.course_generation_service import CourseGenerationService
from app.services.medical_teacher.lesson_generation_service import LessonGenerationService
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService
from app.services.medical_teacher.rag_service import DocumentRagService
from app.services.medical_teacher.tutor_service import LessonTutorService
from app.services.medical_teacher.question_generation_service import QuestionGenerationService
from app.services.medical_teacher.quiz_engine_service import (
  QUIZ_COUNTS,
  QUIZ_DIFFICULTIES,
  QUIZ_MODES,
  QUIZ_SCOPES,
  LearningQuizEngineService,
)
from app.services.medical_teacher.flashcard_service import LearningFlashcardService
from app.services.medical_teacher.teach_me_service import TeachMeService
from app.services.medical_teacher.adaptive_learning_service import AdaptiveLearningService


def _collect_upload_files():
  files = []
  if "files" in request.files:
    files.extend(request.files.getlist("files"))
  if "files[]" in request.files:
    files.extend(request.files.getlist("files[]"))
  if "file" in request.files:
    files.append(request.files.get("file"))
  seen = set()
  unique = []
  for f in files:
    key = id(f)
    if key in seen:
      continue
    seen.add(key)
    unique.append(f)
  return unique


def upload_books():
  """Upload medical documents without extraction."""
  files = _collect_upload_files()
  title = request.form.get("title")
  result = DocumentService.upload_documents(current_user.id, files, title=title)
  if not result.success:
    return error_response(
      "Document upload validation failed.",
      400,
      {"errors": result.errors, **result.to_dict()},
    )
  return success_response("Documents uploaded.", result.to_dict(), 201)


def upload_and_extract():
  """Module 1 pipeline: upload → validate → extract → store."""
  files = _collect_upload_files()
  title = request.form.get("title")
  payload = DocumentService.upload_and_extract(current_user.id, files, title=title)
  upload = payload.get("upload") or {}
  if not upload.get("success"):
    return error_response(
      "Document upload validation failed.",
      400,
      {"errors": upload.get("errors", []), **payload},
    )

  extractions = payload.get("extractions") or []
  any_ok = any(e.get("success") for e in extractions)
  status_code = 201 if any_ok else 422
  message = (
    "Documents uploaded and text extracted."
    if any_ok
    else "Documents uploaded but text extraction failed."
  )
  return success_response(message, payload, status_code)


def upload_and_process():
  """Upload documents and enqueue durable background extraction jobs."""
  files = _collect_upload_files()
  title = request.form.get("title")
  upload = DocumentService.upload_documents(current_user.id, files, title=title)
  if not upload.success:
    return error_response(
      "Document upload validation failed.",
      400,
      {"errors": upload.errors, **upload.to_dict()},
    )

  items = []
  for uploaded in upload.books:
    book = DocumentService.get_book(uploaded.book_id, user_id=current_user.id)
    if not book:
      continue
    job = DocumentProcessingJobService.enqueue(book, current_user.id)
    items.append(
      {
        "book": book.to_dict(),
        "duplicate": uploaded.duplicate,
        "job": job.to_dict() if job else None,
        "ready": job is None and bool(
          book.generated_course
          and book.generated_course.generation_status == "ready"
          and book.generated_course.lesson_generation_status == "ready"
          and book.rag_status == "ready"
          and book.generated_course.question_generation_status == "ready"
          and book.generated_course.quiz_generation_status == "ready"
          and book.generated_course.flashcard_generation_status == "ready"
        ),
      }
    )

  return success_response(
    "Documents uploaded and queued for processing.",
    {"upload": upload.to_dict(), "items": items},
    202,
  )


def list_processing_jobs():
  limit = request.args.get("limit", 20, type=int)
  jobs = DocumentProcessingJobService.list_owned(current_user.id, limit=limit or 20)
  return success_response(
    "Document processing jobs retrieved.",
    {"jobs": [job.to_dict() for job in jobs], "total": len(jobs)},
  )


def get_processing_job(job_id: str):
  job = DocumentProcessingJobService.get_owned(job_id, current_user.id)
  if not job:
    return error_response("Processing job not found.", 404)
  return success_response("Document processing job retrieved.", {"job": job.to_dict()})


def retry_processing_job(job_id: str):
  job = DocumentProcessingJobService.get_owned(job_id, current_user.id)
  if not job:
    return error_response("Processing job not found.", 404)
  if job.status not in ("failed", "cancelled"):
    return error_response("Only failed or cancelled jobs can be retried.", 409, {"job": job.to_dict()})
  job = DocumentProcessingJobService.retry(job)
  return success_response("Document processing job queued again.", {"job": job.to_dict()})


def extract_book(book_id: int):
  """Extract text from an already uploaded book."""
  try:
    book = DocumentService.extract_document(book_id, user_id=current_user.id)
  except LookupError:
    return error_response("Book not found.", 404)
  except FileNotFoundError as exc:
    return error_response(str(exc), 404)
  except RuntimeError as exc:
    failed = DocumentService.get_book(book_id, user_id=current_user.id)
    return error_response(
      str(exc),
      422,
      {"book": failed.to_dict() if failed else None},
    )

  return success_response(
    "Document text extracted.",
    {
      "book": book.to_dict(include_structure=True),
      "text_preview": (book.extracted_text or "")[:1000],
    },
  )


def detect_book_structure(book_id: int):
  """Phase 3: detect a grounded hierarchy without creating course entities."""
  try:
    structure = DocumentStructureService.detect_for_book(book_id, user_id=current_user.id)
  except LookupError:
    return error_response("Book not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 409)
  return success_response(
    "Document structure detected.",
    {"book_id": book_id, "structure": structure},
  )


def get_book_structure(book_id: int):
  book = DocumentService.get_book(book_id, user_id=current_user.id)
  if not book:
    return error_response("Book not found.", 404)
  structure = DocumentStructureService.get_for_book(book)
  if not structure:
    return error_response("Document structure has not been detected yet.", 409)
  return success_response(
    "Document structure retrieved.",
    {"book_id": book.id, "structure": structure},
  )


def generate_book_course(book_id: int):
  """Phase 4: persist the detected hierarchy as a private LMS course."""
  try:
    result = CourseGenerationService.generate_from_book(book_id, user_id=current_user.id)
  except LookupError:
    return error_response("Book not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 409)
  status_code = 200 if result.reused else 201
  message = "Existing generated course retrieved." if result.reused else "Course generated from document structure."
  return success_response(message, result.to_dict(), status_code)


def get_book_course(book_id: int):
  book = DocumentService.get_book(book_id, user_id=current_user.id)
  if not book:
    return error_response("Book not found.", 404)
  course = CourseGenerationService.get_owned_for_book(book.id, current_user.id)
  if not course:
    return error_response("Course has not been generated yet.", 409)
  return success_response(
    "Generated course retrieved.",
    {"course": CourseGenerationService.serialize_course(course)},
  )


def generate_book_lessons(book_id: int):
  payload = request.get_json(silent=True) or {}
  difficulty = str(payload.get("difficulty") or "intermediate")
  use_ai_raw = payload.get("use_ai")
  use_ai = None if use_ai_raw is None else str(use_ai_raw).lower() in ("1", "true", "yes")
  try:
    result = LessonGenerationService.generate_for_book(
      book_id,
      current_user.id,
      difficulty=difficulty,
      use_ai=use_ai,
    )
  except LookupError:
    return error_response("Book not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 409)
  status_code = 201 if result.created_count else 200
  return success_response(
    "Lessons generated from grounded course topics." if result.created_count else "Existing generated lessons retrieved.",
    result.to_dict(include_content=False),
    status_code,
  )


def list_book_lessons(book_id: int):
  include_content = (request.args.get("include_content") or "false").lower() in ("1", "true", "yes")
  try:
    result = LessonGenerationService.list_owned_for_book(book_id, current_user.id)
  except LookupError:
    return error_response("Course not found.", 404)
  return success_response(
    "Generated lessons retrieved.",
    result.to_dict(include_content=include_content),
  )


def index_book(book_id: int):
  payload = request.get_json(silent=True) or {}
  force = str(payload.get("force") or "false").lower() in ("1", "true", "yes")
  try:
    result = DocumentRagService.index_book(book_id, current_user.id, force=force)
  except LookupError:
    return error_response("Book not found.", 404)
  except (ValueError, RuntimeError) as exc:
    return error_response(str(exc), 409 if isinstance(exc, ValueError) else 422)
  return success_response(
    "Existing document index retrieved." if result.reused else "Document search index created.",
    result.to_dict(),
    200 if result.reused else 201,
  )


def get_book_index(book_id: int):
  try:
    status = DocumentRagService.status(book_id, current_user.id)
  except LookupError:
    return error_response("Book not found.", 404)
  return success_response("Document index status retrieved.", status)


def search_book(book_id: int):
  payload = request.get_json(silent=True) or {}
  try:
    topic_id = int(payload["topic_id"]) if payload.get("topic_id") is not None else None
    result = DocumentRagService.search(
      book_id,
      current_user.id,
      str(payload.get("query") or ""),
      limit=int(payload.get("limit") or 5),
      topic_id=topic_id,
    )
  except LookupError:
    return error_response("Book not found.", 404)
  except (TypeError, ValueError) as exc:
    return error_response(str(exc), 400 if "query" in str(exc).lower() else 409)
  except RuntimeError as exc:
    return error_response(str(exc), 422)
  return success_response("Grounded document passages retrieved.", result)


def get_tutor_configuration(book_id: int):
  book = DocumentService.get_book(book_id, user_id=current_user.id)
  if not book:
    return error_response("Book not found.", 404)
  return success_response("Lesson tutor configuration retrieved.", LessonTutorService.configuration())


def create_tutor_session(book_id: int):
  payload = request.get_json(silent=True) or {}
  try:
    lesson_id = int(payload.get("lesson_id"))
  except (TypeError, ValueError):
    return error_response("A valid lesson_id is required.", 400)
  try:
    session = LessonTutorService.create_session(
      book_id,
      current_user.id,
      lesson_id=lesson_id,
      mode=str(payload.get("mode") or "beginner"),
      language=str(payload.get("language") or "en"),
    )
  except LookupError as exc:
    return error_response(str(exc), 404)
  except ValueError as exc:
    return error_response(str(exc), 409)
  return success_response("Lesson tutor session created.", {"session": session.to_dict(include_messages=True)}, 201)


def list_tutor_sessions(book_id: int):
  try:
    sessions = LessonTutorService.list_sessions(
      book_id,
      current_user.id,
      limit=request.args.get("limit", 20, type=int) or 20,
    )
  except LookupError:
    return error_response("Book not found.", 404)
  return success_response(
    "Lesson tutor sessions retrieved.",
    {"sessions": [session.to_dict() for session in sessions], "total": len(sessions)},
  )


def get_tutor_session(book_id: int, session_id: str):
  try:
    session = LessonTutorService.get_session(book_id, current_user.id, session_id)
  except LookupError:
    return error_response("Tutor session not found.", 404)
  return success_response("Lesson tutor session retrieved.", {"session": session.to_dict(include_messages=True)})


def ask_tutor(book_id: int, session_id: str):
  payload = request.get_json(silent=True) or {}
  try:
    result = LessonTutorService.ask(
      book_id,
      current_user.id,
      session_id,
      message=str(payload.get("message") or ""),
      mode=str(payload["mode"]) if payload.get("mode") is not None else None,
      language=str(payload["language"]) if payload.get("language") is not None else None,
    )
  except LookupError:
    return error_response("Tutor session not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 400)
  except RuntimeError:
    return error_response("The lesson tutor is temporarily unavailable. Please try again.", 503)
  return success_response("Grounded tutor response ready.", result, 201)


def get_teach_me_configuration(book_id: int):
  book = DocumentService.get_book(book_id, user_id=current_user.id)
  if not book:
    return error_response("Book not found.", 404)
  return success_response("Teach Me configuration retrieved.", TeachMeService.configuration())


def create_teach_me_session(book_id: int):
  payload = request.get_json(silent=True) or {}
  try:
    lesson_id = int(payload.get("lesson_id"))
  except (TypeError, ValueError):
    return error_response("A valid lesson_id is required.", 400)
  try:
    session, reused = TeachMeService.create_session(
      book_id,
      current_user.id,
      lesson_id=lesson_id,
      difficulty=str(payload.get("difficulty") or "beginner"),
      language=str(payload.get("language") or "en"),
      restart=str(payload.get("restart") or "false").lower() in ("1", "true", "yes"),
    )
  except LookupError as exc:
    return error_response(str(exc), 404)
  except ValueError as exc:
    return error_response(str(exc), 409)
  return success_response(
    "Active Teach Me session resumed." if reused else "Guided Teach Me session created.",
    {"session": TeachMeService.serialize(session), "reused": reused},
    200 if reused else 201,
  )


def list_teach_me_sessions(book_id: int):
  try:
    sessions = TeachMeService.list_sessions(
      book_id,
      current_user.id,
      limit=request.args.get("limit", 20, type=int) or 20,
    )
  except LookupError:
    return error_response("Book not found.", 404)
  return success_response("Teach Me sessions retrieved.", {
    "sessions": [TeachMeService.serialize(session) for session in sessions],
    "total": len(sessions),
  })


def get_teach_me_session(book_id: int, session_id: str):
  try:
    session = TeachMeService.get_session(book_id, current_user.id, session_id)
  except LookupError:
    return error_response("Teach Me session not found.", 404)
  return success_response("Teach Me session retrieved.", {"session": TeachMeService.serialize(session)})


def advance_teach_me_session(book_id: int, session_id: str):
  try:
    result = TeachMeService.advance(book_id, current_user.id, session_id)
  except LookupError:
    return error_response("Teach Me session not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 400)
  return success_response("Teach Me session advanced.", result)


def answer_teach_me_session(book_id: int, session_id: str):
  payload = request.get_json(silent=True) or {}
  try:
    result = TeachMeService.answer(
      book_id,
      current_user.id,
      session_id,
      str(payload.get("answer") or ""),
    )
  except LookupError:
    return error_response("Teach Me session not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 400)
  return success_response("Checkpoint evaluated against the uploaded material.", result, 201)


def get_book_adaptive_learning(book_id: int):
  refresh = (request.args.get("refresh") or "true").lower() in ("1", "true", "yes")
  try:
    result = AdaptiveLearningService.get_snapshot(book_id, current_user.id, refresh=refresh)
  except LookupError:
    return error_response("Book not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 409)
  return success_response("Adaptive topic mastery retrieved.", result)


def refresh_book_adaptive_learning(book_id: int):
  try:
    result = AdaptiveLearningService.refresh_book(book_id, current_user.id)
  except LookupError:
    return error_response("Book not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 409)
  return success_response("Adaptive topic mastery refreshed from current learning evidence.", result)


def generate_book_questions(book_id: int):
  payload = request.get_json(silent=True) or {}
  try:
    count = int(payload.get("count_per_topic") or current_app.config.get("TEACHER_QUESTIONS_PER_TOPIC", 5))
    types = payload.get("question_types")
    if types is not None and not isinstance(types, list):
      return error_response("question_types must be an array.", 400)
    result = QuestionGenerationService.generate_for_book(
      book_id,
      current_user.id,
      count_per_topic=count,
      difficulty=str(payload.get("difficulty") or "mixed"),
      question_types=types,
      force=str(payload.get("force") or "false").lower() in ("1", "true", "yes"),
    )
  except LookupError:
    return error_response("Book not found.", 404)
  except (TypeError, ValueError) as exc:
    detail = str(exc)
    status = 409 if "must be generated" in detail or "index must be ready" in detail else 400
    return error_response(detail, status)
  return success_response(
    "Study questions generated from uploaded material." if result.created_count else "Existing study questions retrieved.",
    result.to_dict(include_answers=False),
    201 if result.created_count else 200,
  )


def list_book_questions(book_id: int):
  try:
    result = QuestionGenerationService.list_owned(
      book_id,
      current_user.id,
      lesson_id=request.args.get("lesson_id", type=int),
      question_type=request.args.get("question_type"),
      difficulty=request.args.get("difficulty"),
      priority=request.args.get("priority"),
    )
  except LookupError:
    return error_response("Book not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 409)
  return success_response("Study questions retrieved.", result.to_dict(include_answers=False))


def get_book_question_answer(book_id: int, question_id: int):
  try:
    question = QuestionGenerationService.get_answer(book_id, current_user.id, question_id)
  except LookupError:
    return error_response("Study question not found.", 404)
  return success_response(
    "Study question answer retrieved.",
    {"question": question.to_dict(include_answer=True)},
  )


def get_book_quiz_configuration(book_id: int):
  book = DocumentService.get_book(book_id, user_id=current_user.id)
  if not book:
    return error_response("Book not found.", 404)
  course = book.generated_course
  if not course:
    return error_response("Course has not been generated yet.", 409)
  return success_response("Quiz configuration retrieved.", {
    "question_counts": list(QUIZ_COUNTS),
    "difficulties": list(QUIZ_DIFFICULTIES),
    "scopes": list(QUIZ_SCOPES),
    "question_modes": list(QUIZ_MODES),
    "modules": [{"id": item.id, "title": item.title} for item in course.modules.all()],
    "topics": [{"id": item.id, "module_id": item.module_id, "title": item.title} for item in course.topics.all()],
  })


def generate_book_quiz(book_id: int):
  payload = request.get_json(silent=True) or {}
  try:
    scope_id = int(payload["scope_id"]) if payload.get("scope_id") is not None else None
    result = LearningQuizEngineService.generate_for_book(
      book_id,
      current_user.id,
      question_count=int(payload.get("question_count") or 10),
      difficulty=str(payload.get("difficulty") or "mixed"),
      scope_type=str(payload.get("scope_type") or "entire_course"),
      scope_id=scope_id,
      question_mode=str(payload.get("question_mode") or "mixed"),
      force=str(payload.get("force") or "false").lower() in ("1", "true", "yes"),
    )
  except LookupError:
    return error_response("Book not found.", 404)
  except (TypeError, ValueError) as exc:
    detail = str(exc)
    precondition = "must be ready" in detail or "have not been generated" in detail or "Complete at least" in detail
    return error_response(detail, 409 if precondition else 400)
  return success_response(
    "Existing generated quiz retrieved." if result.reused else "Private quiz generated from uploaded material.",
    result.to_dict(),
    200 if result.reused else 201,
  )


def list_book_quizzes(book_id: int):
  try:
    quizzes = LearningQuizEngineService.list_owned(book_id, current_user.id)
  except LookupError:
    return error_response("Book not found.", 404)
  return success_response("Generated quizzes retrieved.", {
    "book_id": book_id,
    "quizzes": [item.to_dict() for item in quizzes],
    "total": len(quizzes),
  })


def get_book_quiz(book_id: int, quiz_id: int):
  try:
    quiz = LearningQuizEngineService.get_owned(book_id, current_user.id, quiz_id)
  except LookupError:
    return error_response("Generated quiz not found.", 404)
  return success_response("Generated quiz retrieved.", {"quiz": quiz.to_dict(include_questions=True)})


def submit_book_quiz(book_id: int, quiz_id: int):
  payload = request.get_json(silent=True) or {}
  try:
    result = LearningQuizEngineService.submit(
      book_id,
      current_user.id,
      quiz_id,
      payload.get("answers"),
      int(payload.get("time_taken_seconds") or 0),
    )
  except LookupError:
    return error_response("Generated quiz not found.", 404)
  except (TypeError, ValueError) as exc:
    return error_response(str(exc), 400)
  return success_response("Quiz submitted and topic performance recorded.", result, 201)


def list_book_quiz_attempts(book_id: int):
  try:
    attempts = LearningQuizEngineService.list_attempts(book_id, current_user.id)
  except LookupError:
    return error_response("Book not found.", 404)
  return success_response("Quiz attempts retrieved.", {
    "book_id": book_id,
    "attempts": [item.to_dict() for item in attempts],
    "total": len(attempts),
  })


def generate_book_flashcards(book_id: int):
  payload = request.get_json(silent=True) or {}
  styles = payload.get("styles")
  if styles is not None and not isinstance(styles, list):
    return error_response("styles must be an array.", 400)
  try:
    result = LearningFlashcardService.generate_for_book(
      book_id,
      current_user.id,
      styles=styles,
      force=str(payload.get("force") or "false").lower() in ("1", "true", "yes"),
    )
  except LookupError:
    return error_response("Book not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 409 if "must be ready" in str(exc) else 400)
  return success_response(
    "Existing grounded flashcards retrieved." if result.reused_count else "Flashcards generated from uploaded material.",
    result.to_dict(current_user.id),
    200 if result.reused_count else 201,
  )


def list_book_flashcards(book_id: int):
  try:
    result = LearningFlashcardService.list_owned(
      book_id,
      current_user.id,
      style=request.args.get("style"),
      lesson_id=request.args.get("lesson_id", type=int),
      status=request.args.get("status"),
      due_only=(request.args.get("due_only") or "false").lower() in ("1", "true", "yes"),
    )
  except LookupError:
    return error_response("Book not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 400)
  return success_response("Grounded flashcards retrieved.", result)


def review_book_flashcard(book_id: int, card_id: int):
  payload = request.get_json(silent=True) or {}
  try:
    result = LearningFlashcardService.review(
      book_id,
      current_user.id,
      card_id,
      str(payload.get("action") or ""),
    )
  except LookupError:
    return error_response("Flashcard not found.", 404)
  except ValueError as exc:
    return error_response(str(exc), 400)
  return success_response("Flashcard review recorded.", result)


def parse_book(book_id: int):
  """Module 2: split chapters and analyze medical content."""
  use_ai_raw = request.args.get("use_ai")
  if use_ai_raw is None and request.is_json:
    use_ai_raw = (request.get_json(silent=True) or {}).get("use_ai")
  if use_ai_raw is None:
    use_ai = bool(current_app.config.get("TEACHER_USE_AI", True))
  else:
    use_ai = str(use_ai_raw).lower() in ("1", "true", "yes")

  result = BookParser.parse_book(book_id, user_id=current_user.id, use_ai=use_ai)
  if not result.success:
    status = 404 if result.error_code == "not_found" else 422
    return error_response(result.message, status, result.to_dict())
  return success_response(result.message, result.to_dict())


def list_chapters(book_id: int):
  book = DocumentService.get_book(book_id, user_id=current_user.id)
  if not book:
    return error_response("Book not found.", 404)
  chapters = Chapter.query.filter_by(book_id=book.id).order_by(Chapter.order_index).all()
  return success_response(
    "Chapters retrieved.",
    {
      "book_id": book.id,
      "chapters": [c.to_dict() for c in chapters],
      "total": len(chapters),
      "analysis": book.analysis_json,
      "parse_method": book.parse_method,
    },
  )


def get_chapter(book_id: int, chapter_id: int):
  book = DocumentService.get_book(book_id, user_id=current_user.id)
  if not book:
    return error_response("Book not found.", 404)
  chapter = Chapter.query.filter_by(id=chapter_id, book_id=book.id).first()
  if not chapter:
    return error_response("Chapter not found.", 404)
  include_content = (request.args.get("include_content") or "true").lower() in ("1", "true", "yes")
  return success_response(
    "Chapter retrieved.",
    {"chapter": chapter.to_dict(include_content=include_content)},
  )


def list_books():
  books = DocumentService.list_books(current_user.id)
  return success_response(
    "Books retrieved.",
    {"books": [b.to_dict() for b in books], "total": len(books)},
  )


def get_book(book_id: int):
  include_text = (request.args.get("include_text") or "").lower() in ("1", "true", "yes")
  include_structure = (request.args.get("include_structure") or "true").lower() in ("1", "true", "yes")
  include_analysis = (request.args.get("include_analysis") or "true").lower() in ("1", "true", "yes")
  include_chapters = (request.args.get("include_chapters") or "true").lower() in ("1", "true", "yes")
  book = DocumentService.get_book(book_id, user_id=current_user.id)
  if not book:
    return error_response("Book not found.", 404)
  return success_response(
    "Book retrieved.",
    {
      "book": book.to_dict(
        include_text=include_text,
        include_structure=include_structure,
        include_analysis=include_analysis,
        include_chapters=include_chapters,
      )
    },
  )


def delete_book(book_id: int):
  deleted = DocumentService.delete_book(book_id, current_user.id)
  if not deleted:
    return error_response("Book not found.", 404)
  return success_response("Book deleted.")
