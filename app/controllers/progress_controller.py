from flask_jwt_extended import current_user

from app.helpers.response import success_response
from app.models.course_model import CompletedLesson, Lesson
from app.models.quiz_model import Result
from app.models.simulation_model import SimulationAttempt
from app.services.learning_dashboard_service import LearningDashboardService
from app.services.learning_service import LearningService


def get_progress():
  progress = LearningService.update_learning_progress(current_user.id)
  return success_response("Progress retrieved.", {"progress": progress.to_dict()})


def dashboard():
  progress = LearningService.get_or_create_progress(current_user.id)
  completed_lessons = CompletedLesson.query.filter_by(user_id=current_user.id).count()
  total_lessons = Lesson.query.count()
  quiz_results = Result.query.filter_by(user_id=current_user.id).count()
  sim_attempts = SimulationAttempt.query.filter_by(user_id=current_user.id).count()
  courses_enrolled = (
    CompletedLesson.query.filter_by(user_id=current_user.id)
    .join(Lesson)
    .with_entities(Lesson.course_id)
    .distinct()
    .count()
  )

  avg_quiz = 0
  results = Result.query.filter_by(user_id=current_user.id).all()
  if results:
    avg_quiz = round(sum(r.score for r in results) / len(results), 2)

  return success_response("Dashboard analytics retrieved.", {
    "analytics": {
      "learning_progress": progress.learning_progress,
      "completed_lessons": completed_lessons,
      "total_lessons": total_lessons,
      "courses_engaged": courses_enrolled,
      "quiz_attempts": quiz_results,
      "average_quiz_score": avg_quiz,
      "simulation_attempts": sim_attempts,
      "achievements": progress.achievements or [],
      "weak_topics": progress.weak_topics or [],
    },
  })


def learning_dashboard():
  snapshot = LearningDashboardService.dashboard(current_user.id)
  return success_response("Learning dashboard retrieved.", {"dashboard": snapshot})


def achievements():
  progress = LearningService.get_or_create_progress(current_user.id)
  return success_response("Achievements retrieved.", {
    "achievements": progress.achievements or [],
  })
