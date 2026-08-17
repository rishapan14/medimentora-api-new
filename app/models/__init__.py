"""Import all models so SQLAlchemy registers them with the metadata."""

from app.models.user_model import User
from app.models.report_model import Report
from app.models.report_analysis_model import ReportAnalysis
from app.models.course_model import (
  CompletedLesson,
  Course,
  CourseBookmark,
  CourseCategory,
  CourseModule,
  CourseTopic,
  CourseProgress,
  CourseReview,
  Lesson,
  LessonBookmark,
  LessonResource,
  LessonVideo,
)
from app.models.recommendation_model import Recommendation
from app.models.progress_model import Progress
from app.models.clinical_case_model import ClinicalCase, CaseFavorite
from app.models.simulation_model import Simulation, SimulationAttempt
from app.models.quiz_model import Quiz, Question, QuizAnswer, Result
from app.models.certificate_model import Certificate
from app.models.discussion_model import Discussion, Comment, DiscussionLike, CommentLike
from app.models.notification_model import Notification
from app.models.xray_analysis_model import XrayAnalysis
from app.models.xray_reference_model import XrayReferenceImage
from app.models.reference_xray_library_model import ReferenceXrayLibrary
from app.models.platform_setting_model import PlatformSetting
from app.models.book_model import Book, Chapter, DocumentProcessingJob
from app.models.rag_model import ChunkEmbedding, DocumentChunk
from app.models.tutor_model import TutorMessage, TutorSession
from app.models.adaptive_learning_model import LearningTopicMastery
from app.models.learning_activity_model import LearningActivity
from app.models.body_system_model import (
  BodySystem,
  BodySystemCourse,
  BodySystemProgress,
  BodySystemQuiz,
  HubCertificate,
  HubDisease,
  HubDiseaseClinicalCase,
  HubFlashcard,
  HubFlashcardFavorite,
  HubRecommendation,
  Organ,
  OrganLesson,
)

__all__ = [
  "User",
  "Report",
  "ReportAnalysis",
  "Course",
  "CourseCategory",
  "CourseModule",
  "CourseTopic",
  "Lesson",
  "LessonBookmark",
  "LessonResource",
  "LessonVideo",
  "CompletedLesson",
  "CourseProgress",
  "CourseBookmark",
  "CourseReview",
  "Recommendation",
  "Progress",
  "ClinicalCase",
  "CaseFavorite",
  "Simulation",
  "SimulationAttempt",
  "Quiz",
  "Question",
  "QuizAnswer",
  "Result",
  "Certificate",
  "Discussion",
  "Comment",
  "DiscussionLike",
  "CommentLike",
  "Notification",
  "XrayAnalysis",
  "XrayReferenceImage",
  "ReferenceXrayLibrary",
  "PlatformSetting",
  "Book",
  "Chapter",
  "DocumentProcessingJob",
  "DocumentChunk",
  "ChunkEmbedding",
  "TutorSession",
  "TutorMessage",
  "LearningTopicMastery",
  "LearningActivity",
  "BodySystem",
  "Organ",
  "HubDisease",
  "BodySystemCourse",
  "BodySystemQuiz",
  "OrganLesson",
  "HubDiseaseClinicalCase",
  "HubFlashcard",
  "HubFlashcardFavorite",
  "BodySystemProgress",
  "HubRecommendation",
  "HubCertificate",
]
