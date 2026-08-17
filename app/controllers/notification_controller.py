from flask import request
from flask_jwt_extended import current_user

from app.extensions import db
from app.helpers.response import error_response, success_response
from app.models.notification_model import Notification
from app.services.notification_service import NotificationService
from app.validations.notification_validation import validate_notification


def list_notifications():
  query = Notification.query.filter_by(user_id=current_user.id)
  if request.args.get("unread_only") == "true":
    query = query.filter_by(is_read=False)
  notifications = query.order_by(Notification.created_at.desc()).all()
  return success_response("Notifications retrieved.", {
    "notifications": [n.to_dict() for n in notifications],
    "unread_count": Notification.query.filter_by(user_id=current_user.id, is_read=False).count(),
  })


def mark_read(notification_id):
  notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first()
  if not notification:
    return error_response("Notification not found.", 404)
  notification.is_read = True
  db.session.commit()
  return success_response("Notification marked as read.", {"notification": notification.to_dict()})


def mark_all_read():
  Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
  db.session.commit()
  return success_response("All notifications marked as read.")


def delete_notification(notification_id):
  notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first()
  if not notification:
    return error_response("Notification not found.", 404)
  db.session.delete(notification)
  db.session.commit()
  return success_response("Notification deleted.")


def create_learning_reminder():
  data = request.get_json(silent=True) or {}
  course_title = data.get("course_title", "your course")
  notification = NotificationService.learning_reminder(current_user.id, course_title)
  return success_response("Learning reminder created.", {"notification": notification.to_dict()}, 201)


def create_quiz_reminder():
  data = request.get_json(silent=True) or {}
  quiz_title = data.get("quiz_title", "your quiz")
  notification = NotificationService.quiz_reminder(current_user.id, quiz_title)
  return success_response("Quiz reminder created.", {"notification": notification.to_dict()}, 201)


def create_notification():
  """Admin: create custom notification for a user."""
  data = request.get_json(silent=True)
  errors = validate_notification(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  user_id = data.get("user_id", current_user.id)
  notification = NotificationService.create(
    user_id=user_id,
    notification_type=data["notification_type"],
    title=data["title"],
    message=data["message"],
    reference_id=data.get("reference_id"),
  )
  return success_response("Notification created.", {"notification": notification.to_dict()}, 201)
