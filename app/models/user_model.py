from app.extensions import db
from app.utils import utc_now
from werkzeug.security import check_password_hash, generate_password_hash


class User(db.Model):
  """User account with role-based access."""

  __tablename__ = "users"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  email = db.Column(db.String(120), nullable=False, unique=True, index=True)
  password = db.Column(db.String(255), nullable=False)
  full_name = db.Column(db.String(150), nullable=True)
  role = db.Column(db.String(30), nullable=False, default="medical_student")
  # Clinical/system role restored when demoting from Admin Panel Admin → User
  previous_role = db.Column(db.String(30), nullable=True)
  speciality = db.Column(db.String(100), nullable=True)
  bio = db.Column(db.Text, nullable=True)
  reset_token = db.Column(db.String(255), nullable=True)
  reset_token_expires = db.Column(db.DateTime, nullable=True)
  is_active = db.Column(db.Boolean, default=True)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  # Relationships
  reports = db.relationship("Report", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  report_analyses = db.relationship("ReportAnalysis", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  recommendations = db.relationship("Recommendation", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  progress_records = db.relationship("Progress", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  clinical_cases = db.relationship("ClinicalCase", back_populates="creator", lazy="dynamic")
  quizzes_created = db.relationship(
    "Quiz",
    back_populates="creator",
    lazy="dynamic",
    foreign_keys="Quiz.created_by",
  )
  simulation_attempts = db.relationship("SimulationAttempt", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  quiz_results = db.relationship("Result", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  certificates = db.relationship("Certificate", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  discussions = db.relationship("Discussion", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  comments = db.relationship("Comment", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  notifications = db.relationship("Notification", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  bookmarks = db.relationship("LessonBookmark", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  completed_lessons = db.relationship("CompletedLesson", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  case_favorites = db.relationship("CaseFavorite", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  xray_analyses = db.relationship("XrayAnalysis", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  course_progress = db.relationship("CourseProgress", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  course_bookmarks = db.relationship("CourseBookmark", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")
  course_reviews = db.relationship("CourseReview", back_populates="user", lazy="dynamic", cascade="all, delete-orphan")

  def set_password(self, password):
    self.password = generate_password_hash(password)

  def check_password(self, password):
    return check_password_hash(self.password, password)

  @property
  def is_admin(self) -> bool:
    from app.constants import is_admin_role

    return is_admin_role(self.role)

  def to_dict(self, include_email=True):
    data = {
      "id": self.id,
      "full_name": self.full_name,
      "role": self.role,
      "previous_role": self.previous_role,
      "is_admin": self.is_admin,
      # Frontend alias used by Admin Panel guards
      "isAdmin": self.is_admin,
      # Binary Admin Panel label (Admin vs User)
      "panel_role": "Admin" if self.is_admin else "User",
      "speciality": self.speciality,
      "bio": self.bio,
      "is_active": self.is_active,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_email:
      data["email"] = self.email
    return data
