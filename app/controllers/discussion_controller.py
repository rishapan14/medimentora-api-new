from flask import request
from flask_jwt_extended import current_user
from sqlalchemy import or_

from app.extensions import db
from app.helpers.response import error_response, success_response
from app.models.discussion_model import Comment, CommentLike, Discussion, DiscussionLike
from app.validations.discussion_validation import validate_comment, validate_discussion


def list_discussions():
  query = Discussion.query
  if request.args.get("speciality"):
    query = query.filter_by(speciality=request.args.get("speciality"))
  if request.args.get("search"):
    term = f"%{request.args.get('search')}%"
    query = query.filter(or_(Discussion.title.ilike(term), Discussion.content.ilike(term)))
  discussions = query.order_by(Discussion.created_at.desc()).all()
  liked_ids = {
    like.discussion_id
    for like in DiscussionLike.query.filter_by(user_id=current_user.id).all()
  }
  return success_response("Discussions retrieved.", {
    "discussions": [
      {**d.to_dict(), "liked_by_current_user": d.id in liked_ids}
      for d in discussions
    ],
  })


def get_discussion(discussion_id):
  discussion = Discussion.query.get(discussion_id)
  if not discussion:
    return error_response("Discussion not found.", 404)
  return success_response("Discussion retrieved.", {
    "discussion": discussion.to_dict(include_comments=True),
  })


def create_discussion():
  data = request.get_json(silent=True)
  errors = validate_discussion(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  discussion = Discussion(
    user_id=current_user.id,
    title=data["title"],
    content=data["content"],
    speciality=data.get("speciality"),
  )
  db.session.add(discussion)
  db.session.commit()
  return success_response("Discussion created.", {"discussion": discussion.to_dict()}, 201)


def update_discussion(discussion_id):
  discussion = Discussion.query.get(discussion_id)
  if not discussion:
    return error_response("Discussion not found.", 404)
  if discussion.user_id != current_user.id and current_user.role != "admin":
    return error_response("Not authorized.", 403)

  data = request.get_json(silent=True) or {}
  for field in ("title", "content", "speciality"):
    if field in data:
      setattr(discussion, field, data[field])
  db.session.commit()
  return success_response("Discussion updated.", {"discussion": discussion.to_dict()})


def delete_discussion(discussion_id):
  discussion = Discussion.query.get(discussion_id)
  if not discussion:
    return error_response("Discussion not found.", 404)
  if discussion.user_id != current_user.id and current_user.role != "admin":
    return error_response("Not authorized.", 403)
  db.session.delete(discussion)
  db.session.commit()
  return success_response("Discussion deleted.")


def add_comment(discussion_id):
  discussion = Discussion.query.get(discussion_id)
  if not discussion:
    return error_response("Discussion not found.", 404)

  data = request.get_json(silent=True)
  errors = validate_comment(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  parent_id = data.get("parent_id")
  if parent_id:
    parent = Comment.query.filter_by(id=parent_id, discussion_id=discussion_id).first()
    if not parent:
      return error_response("Parent comment not found.", 404)

  comment = Comment(
    discussion_id=discussion_id,
    user_id=current_user.id,
    content=data["content"],
    parent_id=parent_id,
  )
  db.session.add(comment)
  db.session.commit()
  return success_response("Comment added.", {"comment": comment.to_dict()}, 201)


def delete_comment(comment_id):
  comment = Comment.query.get(comment_id)
  if not comment:
    return error_response("Comment not found.", 404)
  if comment.user_id != current_user.id and current_user.role != "admin":
    return error_response("Not authorized.", 403)
  db.session.delete(comment)
  db.session.commit()
  return success_response("Comment deleted.")


def like_discussion(discussion_id):
  discussion = Discussion.query.get(discussion_id)
  if not discussion:
    return error_response("Discussion not found.", 404)

  existing = DiscussionLike.query.filter_by(discussion_id=discussion_id, user_id=current_user.id).first()
  if existing:
    db.session.delete(existing)
    discussion.like_count = max(0, discussion.like_count - 1)
    db.session.commit()
    return success_response("Like removed.", {"like_count": discussion.like_count})

  like = DiscussionLike(discussion_id=discussion_id, user_id=current_user.id)
  discussion.like_count += 1
  db.session.add(like)
  db.session.commit()
  return success_response("Discussion liked.", {"like_count": discussion.like_count})


def like_comment(comment_id):
  comment = Comment.query.get(comment_id)
  if not comment:
    return error_response("Comment not found.", 404)

  existing = CommentLike.query.filter_by(comment_id=comment_id, user_id=current_user.id).first()
  if existing:
    db.session.delete(existing)
    comment.like_count = max(0, comment.like_count - 1)
    db.session.commit()
    return success_response("Like removed.", {"like_count": comment.like_count})

  like = CommentLike(comment_id=comment_id, user_id=current_user.id)
  comment.like_count += 1
  db.session.add(like)
  db.session.commit()
  return success_response("Comment liked.", {"like_count": comment.like_count})
