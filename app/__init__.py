import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from app.config import Config
from app.extensions import db, jwt
from app.helpers.response import error_response
from app.routes import register_blueprints


def create_app():
  """Application factory."""
  app = Flask(__name__)
  app.config.from_object(Config)

  # Resolve relative upload folders against the API project root (parent of app/)
  project_root = os.path.abspath(os.path.join(app.root_path, os.pardir))
  for key in (
    "UPLOAD_FOLDER",
    "REPORT_UPLOAD_FOLDER",
    "CERTIFICATE_UPLOAD_FOLDER",
    "XRAY_UPLOAD_FOLDER",
    "XRAY_HEATMAP_FOLDER",
    "XRAY_PREPROCESSED_FOLDER",
    "XRAY_REFERENCE_LIBRARY_FOLDER",
    "TEACHER_UPLOAD_FOLDER",
  ):
    value = app.config.get(key)
    if value and not os.path.isabs(value):
      app.config[key] = os.path.join(project_root, value)

  # Ensure upload directories exist
  os.makedirs(app.config["REPORT_UPLOAD_FOLDER"], exist_ok=True)
  os.makedirs(app.config["CERTIFICATE_UPLOAD_FOLDER"], exist_ok=True)
  os.makedirs(app.config["XRAY_UPLOAD_FOLDER"], exist_ok=True)
  os.makedirs(app.config["XRAY_HEATMAP_FOLDER"], exist_ok=True)
  os.makedirs(app.config["XRAY_PREPROCESSED_FOLDER"], exist_ok=True)
  os.makedirs(app.config["XRAY_REFERENCE_LIBRARY_FOLDER"], exist_ok=True)
  os.makedirs(app.config["TEACHER_UPLOAD_FOLDER"], exist_ok=True)

  db.init_app(app)
  jwt.init_app(app)
  CORS(
    app,
    resources={
      r"/api/*": {"origins": app.config["CORS_ORIGINS"]},
      r"/health": {"origins": app.config["CORS_ORIGINS"]},
      r"/ready": {"origins": app.config["CORS_ORIGINS"]},
    },
    methods=("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
    allow_headers=("Authorization", "Content-Type", "Accept"),
    expose_headers=("Content-Disposition",),
    supports_credentials=False,
    max_age=600,
  )

  # Import all models so SQLAlchemy registers metadata before create_all()
  from app.models import (  # noqa: F401
    CaseFavorite,
    Certificate,
    ClinicalCase,
    Comment,
    CommentLike,
    CompletedLesson,
    Course,
    CourseBookmark,
    CourseCategory,
    CourseModule,
    CourseProgress,
    CourseReview,
    Discussion,
    DiscussionLike,
    Lesson,
    LessonBookmark,
    LessonResource,
    LessonVideo,
    Notification,
    Progress,
    Question,
    Quiz,
    QuizAnswer,
    Recommendation,
    Report,
    ReportAnalysis,
    Result,
    Simulation,
    SimulationAttempt,
    User,
    XrayAnalysis,
    Book,
    Chapter,
    DocumentProcessingJob,
    PlatformSetting,
    BodySystem,
    Organ,
    HubDisease,
    BodySystemCourse,
    BodySystemQuiz,
    OrganLesson,
    HubDiseaseClinicalCase,
    HubFlashcard,
    HubFlashcardFavorite,
    BodySystemProgress,
    HubRecommendation,
  )

  @jwt.user_lookup_loader
  def user_lookup_callback(_jwt_header, jwt_data):
    from app.models.user_model import User as UserModel
    try:
      user_id = int(jwt_data["sub"])
    except (KeyError, TypeError, ValueError):
      return None
    user = db.session.get(UserModel, user_id)
    # Deactivated accounts must not authorize API calls with existing JWTs
    if user is not None and getattr(user, "is_active", True) is False:
      return None
    return user

  @jwt.user_lookup_error_loader
  def user_lookup_error_callback(_jwt_header, _jwt_data):
    return error_response("Account is deactivated or no longer valid.", 403)

  register_blueprints(app)

  @app.before_request
  def _ensure_schema_once():
    """Gate DB routes until Railway's background schema bootstrap is ready."""
    if request.method == "OPTIONS" or request.path in ("/health", "/ready"):
      return None

    ready_file = os.getenv("SCHEMA_READY_FILE", "").strip()
    if ready_file:
      if not os.path.isfile(ready_file):
        return error_response(
          "Database schema is still initializing. Please retry shortly.",
          503,
          {"error_code": "schema_initializing"},
        )
      app._schema_patched = True
      return None

    if getattr(app, "_schema_patched", False):
      return None
    from app.helpers.schema_patches import (
      ensure_body_systems_hub_schema,
      ensure_learning_schema,
      ensure_medical_teacher_schema,
      ensure_platform_settings_schema,
      ensure_report_history_schema,
      ensure_user_previous_role_schema,
      ensure_xray_analysis_schema,
      ensure_xray_reference_library_schema,
    )

    ensure_report_history_schema()
    ensure_xray_analysis_schema()
    ensure_xray_reference_library_schema()
    ensure_learning_schema()
    ensure_body_systems_hub_schema()
    ensure_medical_teacher_schema()
    ensure_platform_settings_schema()
    ensure_user_previous_role_schema()
    app._schema_patched = True
    return None

  @app.before_request
  def _enforce_maintenance_mode():
    """Block non-admin API traffic while maintenance mode is on."""
    from flask import request
    from flask_jwt_extended import verify_jwt_in_request

    path = request.path or ""
    if not path.startswith("/api/"):
      return None
    # Public / admin-exempt endpoints
    exempt_prefixes = (
      "/api/auth/login",
      "/api/auth/refresh",
      "/api/auth/forgot-password",
      "/api/auth/reset-password",
      "/api/platform/",
      "/api/admin/",
    )
    if path == "/api/auth/register":
      return None  # handled inside register controller
    if any(path.startswith(p) for p in exempt_prefixes):
      return None
    if path in ("/", "/api", "/api/"):
      return None

    try:
      from app.services.admin.settings_admin_service import AdminSettingsService

      if not AdminSettingsService.get_bool("maintenance_mode", False):
        return None
    except Exception:
      return None

    # Allow admins with a valid JWT; block everyone else
    try:
      verify_jwt_in_request(optional=True)
    except Exception:
      return error_response(
        "MediMentora is temporarily in maintenance mode. Please try again later.",
        503,
        {"error_code": "maintenance_mode"},
      )

    from flask_jwt_extended import current_user as jwt_user

    from app.constants import is_admin_role

    if jwt_user is not None and is_admin_role(getattr(jwt_user, "role", None)):
      return None
    return error_response(
      "MediMentora is temporarily in maintenance mode. Please try again later.",
      503,
      {"error_code": "maintenance_mode"},
    )

  @app.route("/", methods=["GET"])
  def api_home():
    return jsonify({
      "status": "success",
      "message": "AI-Powered Clinical Report Analysis & Nursing Assistance Platform API",
      "data": {
        "version": "1.0.0",
        "docs": {
          "xray_swagger_ui": "/apidocs",
          "xray_openapi": "/apispec/xray.yaml",
          "xray_openapi_meta": "/apispec/xray",
        },
        "modules": {
          "auth": "/api/auth",
          "reports": "/api/reports",
          "analysis": "/api/analysis",
          "learning": "/api/learning",
          "medical_teacher": "/api/medical-teacher",
          "xray": "/api/xray",
          "clinical_cases": "/api/clinical-cases",
          "simulations": "/api/simulations",
          "quizzes": "/api/quizzes",
          "progress": "/api/progress",
          "certificates": "/api/certificates",
          "discussions": "/api/discussions",
          "notifications": "/api/notifications",
        },
      },
    })

  @app.route("/health", methods=["GET"])
  def health_check():
    """Unauthenticated liveness endpoint for Railway and the frontend."""
    return jsonify({"status": "ok", "service": "medimentora-api"}), 200

  @app.route("/ready", methods=["GET"])
  def readiness_check():
    """Verify schema bootstrap, live MySQL connectivity, and table presence."""
    ready_file = os.getenv("SCHEMA_READY_FILE", "").strip()
    if ready_file and not os.path.isfile(ready_file):
      return jsonify({
        "status": "starting",
        "service": "medimentora-api",
        "database_schema": "initializing",
      }), 503
    try:
      with db.engine.connect() as connection:
        connection.execute(text("SELECT 1"))
      table_count = len(inspect(db.engine).get_table_names())
    except SQLAlchemyError:
      return jsonify({
        "status": "error",
        "service": "medimentora-api",
        "database_schema": "unreachable",
      }), 503
    if table_count == 0:
      return jsonify({
        "status": "starting",
        "service": "medimentora-api",
        "database_schema": "empty",
      }), 503
    return jsonify({
      "status": "ok",
      "service": "medimentora-api",
      "database_schema": "ready",
      "table_count": table_count,
    }), 200

  @app.errorhandler(400)
  def bad_request(err):
    return error_response(getattr(err, "description", "Bad request."), 400)

  @app.errorhandler(404)
  def not_found(err):
    return error_response("Resource not found.", 404)

  @app.errorhandler(405)
  def method_not_allowed(err):
    return error_response("Method not allowed.", 405)

  @app.errorhandler(OperationalError)
  def handle_operational_error(err):
    db.session.rollback()
    orig = getattr(err, "orig", None)
    code = orig.args[0] if orig and orig.args else None
    if code == 1049:
      return error_response("Invalid database name configured.", 500)
    if code in (2003, 2002):
      return error_response("MySQL server is not running or not reachable.", 503)
    return error_response("Database connection failed.", 500)

  @app.errorhandler(ProgrammingError)
  def handle_programming_error(err):
    db.session.rollback()
    return error_response("Database schema error.", 500)

  @app.errorhandler(500)
  def handle_internal_error(err):
    db.session.rollback()
    return error_response("An internal server error occurred.", 500)

  if os.getenv("RUN_SCHEMA_BOOTSTRAP_BACKGROUND", "false").lower() == "true":
    ready_file = os.getenv("SCHEMA_READY_FILE", "/tmp/medimentora-schema-ready")

    def _bootstrap_schema_in_background():
      marker = Path(ready_file)
      if marker.is_file():
        app.logger.info("Database schema readiness marker already exists")
        return
      retry_seconds = float(os.getenv("SCHEMA_BOOTSTRAP_RETRY_SECONDS", "10"))
      while True:
        try:
          from app.schema_bootstrap import bootstrap_schema

          bootstrap_schema(app)
          marker.touch()
          app.logger.info("Database schema is ready")
          return
        except Exception:
          app.logger.exception(
            "Database schema bootstrap failed; retrying in %s seconds",
            retry_seconds,
          )
          time.sleep(retry_seconds)

    threading.Thread(
      target=_bootstrap_schema_in_background,
      name="schema-bootstrap",
      daemon=True,
    ).start()

  return app
