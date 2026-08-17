"""AI Medical Teacher package — document processing, book parsing, later teaching modules."""

from app.services.medical_teacher.book_parser import BookParser
from app.services.medical_teacher.course_generation_service import CourseGenerationService
from app.services.medical_teacher.lesson_generation_service import LessonGenerationService
from app.services.medical_teacher.document_service import DocumentService
from app.services.medical_teacher.document_structure_service import DocumentStructureService
from app.services.medical_teacher.rag_service import DocumentRagService
from app.services.medical_teacher.tutor_service import LessonTutorService
from app.services.medical_teacher.question_generation_service import QuestionGenerationService
from app.services.medical_teacher.quiz_engine_service import LearningQuizEngineService
from app.services.medical_teacher.flashcard_service import LearningFlashcardService
from app.services.medical_teacher.teach_me_service import TeachMeService
from app.services.medical_teacher.adaptive_learning_service import AdaptiveLearningService

__all__ = [
  "DocumentService",
  "DocumentStructureService",
  "CourseGenerationService",
  "LessonGenerationService",
  "DocumentRagService",
  "LessonTutorService",
  "QuestionGenerationService",
  "LearningQuizEngineService",
  "LearningFlashcardService",
  "TeachMeService",
  "AdaptiveLearningService",
  "BookParser",
]
