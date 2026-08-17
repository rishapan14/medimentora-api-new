from app.extensions import db
from app.utils import utc_now


class Discussion(db.Model):
  """Discussion thread for community learning."""

  __tablename__ = "discussions"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  title = db.Column(db.String(200), nullable=False)
  content = db.Column(db.Text, nullable=False)
  speciality = db.Column(db.String(100), nullable=True)
  like_count = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  user = db.relationship("User", back_populates="discussions")
  comments = db.relationship("Comment", back_populates="discussion", lazy="dynamic", cascade="all, delete-orphan")
  likes = db.relationship("DiscussionLike", back_populates="discussion", lazy="dynamic", cascade="all, delete-orphan")

  def to_dict(self, include_comments=False):
    data = {
      "id": self.id,
      "user_id": self.user_id,
      "author": self.user.to_dict(include_email=False) if self.user else None,
      "title": self.title,
      "content": self.content,
      "speciality": self.speciality,
      "like_count": self.like_count,
      "comment_count": self.comments.count(),
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_comments:
      data["comments"] = [c.to_dict(include_replies=True) for c in self.comments.filter_by(parent_id=None)]
    return data


class Comment(db.Model):
  """Comment or reply on a discussion."""

  __tablename__ = "comments"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  discussion_id = db.Column(db.Integer, db.ForeignKey("discussions.id"), nullable=False, index=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  parent_id = db.Column(
    db.Integer, db.ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True
  )
  content = db.Column(db.Text, nullable=False)
  like_count = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)

  discussion = db.relationship("Discussion", back_populates="comments")
  user = db.relationship("User", back_populates="comments")
  parent = db.relationship(
    "Comment",
    remote_side=[id],
    backref=db.backref("replies", cascade="all, delete-orphan"),
  )
  likes = db.relationship("CommentLike", back_populates="comment", lazy="dynamic", cascade="all, delete-orphan")

  def to_dict(self, include_replies=False):
    data = {
      "id": self.id,
      "discussion_id": self.discussion_id,
      "user_id": self.user_id,
      "parent_id": self.parent_id,
      "author": self.user.to_dict(include_email=False) if self.user else None,
      "content": self.content,
      "like_count": self.like_count,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
    if include_replies:
      data["replies"] = [reply.to_dict() for reply in self.replies]
    return data


class DiscussionLike(db.Model):
  """Like on a discussion."""

  __tablename__ = "discussion_likes"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  discussion_id = db.Column(db.Integer, db.ForeignKey("discussions.id"), nullable=False, index=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  created_at = db.Column(db.DateTime, default=utc_now)

  discussion = db.relationship("Discussion", back_populates="likes")

  __table_args__ = (db.UniqueConstraint("discussion_id", "user_id", name="uq_discussion_user_like"),)


class CommentLike(db.Model):
  """Like on a comment."""

  __tablename__ = "comment_likes"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  comment_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=False, index=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  created_at = db.Column(db.DateTime, default=utc_now)

  comment = db.relationship("Comment", back_populates="likes")

  __table_args__ = (db.UniqueConstraint("comment_id", "user_id", name="uq_comment_user_like"),)
