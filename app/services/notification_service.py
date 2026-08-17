"""Notification creation helpers."""

from app.constants import NOTIF_CERTIFICATE, NOTIF_LEARNING_REMINDER, NOTIF_QUIZ_REMINDER
from app.extensions import db
from app.models.notification_model import Notification


class NotificationService:
  @staticmethod
  def create(user_id, notification_type, title, message, reference_id=None):
    notification = Notification(
      user_id=user_id,
      notification_type=notification_type,
      title=title,
      message=message,
      reference_id=reference_id,
    )
    db.session.add(notification)
    db.session.commit()
    return notification

  @staticmethod
  def learning_reminder(user_id, course_title):
    return NotificationService.create(
      user_id,
      NOTIF_LEARNING_REMINDER,
      "Learning Reminder",
      f"Continue your learning journey — pick up where you left off in {course_title}.",
    )

  @staticmethod
  def quiz_reminder(user_id, quiz_title):
    return NotificationService.create(
      user_id,
      NOTIF_QUIZ_REMINDER,
      "Quiz Reminder",
      f"You have a pending quiz: {quiz_title}. Test your knowledge today!",
    )

  @staticmethod
  def certificate_issued(user_id, course_title, certificate_id):
    return NotificationService.create(
      user_id,
      NOTIF_CERTIFICATE,
      "Certificate Issued",
      f"Congratulations! Your certificate for {course_title} is ready to download.",
      reference_id=certificate_id,
    )
