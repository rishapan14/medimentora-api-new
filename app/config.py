import os
from datetime import timedelta
from sqlalchemy.engine import make_url

from dotenv import load_dotenv

load_dotenv()


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    """Read a comma-separated environment variable into clean values."""
    return tuple(value.strip().rstrip("/") for value in os.getenv(name, default).split(",") if value.strip())


def _mysql_settings(mysql_url: str | None = None) -> dict[str, str]:
    """Validate MYSQL_URL and normalize it for the PyMySQL SQLAlchemy driver."""
    raw_url = (mysql_url if mysql_url is not None else os.getenv("MYSQL_URL", "")).strip()
    if not raw_url:
        raise RuntimeError("MYSQL_URL is required")

    try:
        url = make_url(raw_url)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("MYSQL_URL is invalid") from exc

    if url.get_backend_name() != "mysql":
        raise RuntimeError("MYSQL_URL must use the mysql:// scheme")
    if not url.host or not url.database:
        raise RuntimeError("MYSQL_URL must include a host and database name")

    sqlalchemy_url = url.set(drivername="mysql+pymysql")
    return {
        "url": sqlalchemy_url.render_as_string(hide_password=False),
        "host": url.host,
        "port": str(url.port or 3306),
        "name": url.database,
    }


_MYSQL = _mysql_settings()


class Config:
    """Application configuration loaded from environment variables."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:5000").rstrip("/")
    CORS_ORIGINS = _csv_env(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,https://medimentora-client.vercel.app",
    )

    # MYSQL_URL is the only database connection setting.
    MYSQL_URL = _MYSQL["url"]
    MYSQL_HOST = _MYSQL["host"]
    MYSQL_PORT = _MYSQL["port"]
    MYSQL_DATABASE = _MYSQL["name"]
    SQLALCHEMY_DATABASE_URI = MYSQL_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "30"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7"))
    )

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Gemini (AI Medical Teacher enrichment — optional; heuristic parser works without it)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    TEACHER_USE_AI = os.getenv("TEACHER_USE_AI", "true").lower() == "true"

    # File uploads
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    REPORT_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "reports")
    CERTIFICATE_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "certificates")
    XRAY_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "xrays")
    XRAY_HEATMAP_FOLDER = os.path.join(UPLOAD_FOLDER, "xrays", "heatmaps")
    XRAY_PREPROCESSED_FOLDER = os.path.join(UPLOAD_FOLDER, "xrays", "preprocessed")
    # Educational healthy reference library (Healthy X-Ray Comparison Module 2)
    XRAY_REFERENCE_LIBRARY_FOLDER = os.getenv(
      "XRAY_REFERENCE_LIBRARY_FOLDER", "reference_library"
    )
    XRAY_AUTO_SEED_REFERENCES = os.getenv("XRAY_AUTO_SEED_REFERENCES", "false").lower() == "true"
    # AI Medical Teacher — textbooks / notes / guidelines (Module 1)
    TEACHER_UPLOAD_FOLDER = os.getenv(
      "TEACHER_UPLOAD_FOLDER",
      os.path.join(UPLOAD_FOLDER, "medical_teacher", "books"),
    )
    TEACHER_MAX_FILES = int(os.getenv("TEACHER_MAX_FILES", "5"))
    TEACHER_MAX_FILE_BYTES = int(os.getenv("TEACHER_MAX_FILE_BYTES", str(100 * 1024 * 1024)))  # 100 MB
    TEACHER_MAX_TOTAL_BYTES = int(os.getenv("TEACHER_MAX_TOTAL_BYTES", str(200 * 1024 * 1024)))
    TEACHER_ALLOWED_EXTENSIONS = ("pdf", "docx", "txt")
    TEACHER_STORAGE_BACKEND = os.getenv("TEACHER_STORAGE_BACKEND", "local").strip().lower()
    TEACHER_JOB_POLL_SECONDS = float(os.getenv("TEACHER_JOB_POLL_SECONDS", "2"))
    TEACHER_JOB_LEASE_SECONDS = int(os.getenv("TEACHER_JOB_LEASE_SECONDS", "1800"))
    TEACHER_JOB_MAX_ATTEMPTS = int(os.getenv("TEACHER_JOB_MAX_ATTEMPTS", "3"))
    TEACHER_LESSON_USE_AI = os.getenv("TEACHER_LESSON_USE_AI", "false").lower() == "true"
    TEACHER_LESSON_MAX_SOURCE_CHARS = int(os.getenv("TEACHER_LESSON_MAX_SOURCE_CHARS", "12000"))
    TEACHER_EMBEDDING_PROVIDER = os.getenv("TEACHER_EMBEDDING_PROVIDER", "local_hash").strip().lower()
    TEACHER_EMBEDDING_MODEL = os.getenv("TEACHER_EMBEDDING_MODEL", "medimentora-hash-v1").strip()
    TEACHER_EMBEDDING_DIMENSION = int(os.getenv("TEACHER_EMBEDDING_DIMENSION", "256"))
    TEACHER_OPENAI_EMBEDDING_MODEL = os.getenv("TEACHER_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
    TEACHER_CHUNK_SIZE_CHARS = int(os.getenv("TEACHER_CHUNK_SIZE_CHARS", "1800"))
    TEACHER_CHUNK_OVERLAP_CHARS = int(os.getenv("TEACHER_CHUNK_OVERLAP_CHARS", "250"))
    TEACHER_TUTOR_USE_AI = os.getenv("TEACHER_TUTOR_USE_AI", "true").lower() == "true"
    TEACHER_TUTOR_CONTEXT_CHUNKS = int(os.getenv("TEACHER_TUTOR_CONTEXT_CHUNKS", "5"))
    TEACHER_TUTOR_HISTORY_MESSAGES = int(os.getenv("TEACHER_TUTOR_HISTORY_MESSAGES", "8"))
    TEACHER_TUTOR_MAX_MESSAGE_CHARS = int(os.getenv("TEACHER_TUTOR_MAX_MESSAGE_CHARS", "2000"))
    TEACHER_TUTOR_MAX_SESSION_MESSAGES = int(os.getenv("TEACHER_TUTOR_MAX_SESSION_MESSAGES", "100"))
    TEACHER_QUESTION_USE_AI = os.getenv("TEACHER_QUESTION_USE_AI", "false").lower() == "true"
    TEACHER_QUESTIONS_PER_TOPIC = int(os.getenv("TEACHER_QUESTIONS_PER_TOPIC", "5"))
    TEACHER_QUESTION_MAX_SOURCE_CHARS = int(os.getenv("TEACHER_QUESTION_MAX_SOURCE_CHARS", "8000"))
    TEACHER_DEFAULT_QUIZ_QUESTION_COUNT = int(os.getenv("TEACHER_DEFAULT_QUIZ_QUESTION_COUNT", "10"))
    TEACHER_QUIZ_MINUTES_PER_QUESTION = float(os.getenv("TEACHER_QUIZ_MINUTES_PER_QUESTION", "1.5"))
    TEACHER_FLASHCARD_STYLES = os.getenv("TEACHER_FLASHCARD_STYLES", "easy,medium,hard,exam,nursing,clinical")
    # X-ray upload limits
    XRAY_MAX_FILES = int(os.getenv("XRAY_MAX_FILES", "20"))
    XRAY_MAX_FILE_BYTES = int(os.getenv("XRAY_MAX_FILE_BYTES", str(25 * 1024 * 1024)))  # 25 MB each
    XRAY_MAX_TOTAL_BYTES = int(os.getenv("XRAY_MAX_TOTAL_BYTES", str(100 * 1024 * 1024)))
    XRAY_MIN_WIDTH = int(os.getenv("XRAY_MIN_WIDTH", "64"))
    XRAY_MIN_HEIGHT = int(os.getenv("XRAY_MIN_HEIGHT", "64"))
    XRAY_MAX_WIDTH = int(os.getenv("XRAY_MAX_WIDTH", "10000"))
    XRAY_MAX_HEIGHT = int(os.getenv("XRAY_MAX_HEIGHT", "10000"))
    # Phase 1: JPG/JPEG/PNG + DICOM (.dcm / .dicom)
    XRAY_ALLOWED_EXTENSIONS = tuple(
      e.strip().lower()
      for e in os.getenv(
        "XRAY_ALLOWED_EXTENSIONS", "jpg,jpeg,png,dcm,dicom"
      ).split(",")
      if e.strip()
    )
    # X-ray preprocessing (Module 3)
    XRAY_PREPROCESS_MAX_DIM = int(os.getenv("XRAY_PREPROCESS_MAX_DIM", "2048"))
    XRAY_PREPROCESS_MIN_DIM = int(os.getenv("XRAY_PREPROCESS_MIN_DIM", "512"))
    XRAY_AUTO_PREPROCESS = os.getenv("XRAY_AUTO_PREPROCESS", "true").lower() == "true"
    # X-ray vision model (Module 4): auto | heuristic | onnx
    XRAY_VISION_MODEL = os.getenv("XRAY_VISION_MODEL", "auto")
    XRAY_VISION_ONNX_PATH = os.getenv("XRAY_VISION_ONNX_PATH", "")
    # X-ray heatmap (Module 6)
    XRAY_AUTO_HEATMAP = os.getenv("XRAY_AUTO_HEATMAP", "true").lower() == "true"
    # Educational healthy comparison (Comparison Module 3)
    XRAY_AUTO_COMPARISON = os.getenv("XRAY_AUTO_COMPARISON", "true").lower() == "true"
    # Multi-upload limits: up to 20 files / 100 MB total (request body limit)
    UPLOAD_MAX_FILES = int(os.getenv("UPLOAD_MAX_FILES", "20"))
    UPLOAD_MAX_TOTAL_BYTES = int(os.getenv("UPLOAD_MAX_TOTAL_BYTES", str(100 * 1024 * 1024)))
    UPLOAD_MAX_FILE_BYTES = int(os.getenv("UPLOAD_MAX_FILE_BYTES", str(100 * 1024 * 1024)))
    MAX_CONTENT_LENGTH = int(
        os.getenv("MAX_CONTENT_LENGTH", str(UPLOAD_MAX_TOTAL_BYTES + (2 * 1024 * 1024)))
    )

    # Password reset
    RESET_TOKEN_EXPIRE_HOURS = int(os.getenv("RESET_TOKEN_EXPIRE_HOURS", "24"))

    # Frontend URL (for password reset links in emails — placeholder)
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # OCR pipeline (Module 1 — medical report analysis)
    OCR_ENGINE = os.getenv("OCR_ENGINE", "auto")
    OCR_PREPROCESS = os.getenv("OCR_PREPROCESS", "true").lower() == "true"
    OCR_TIMEOUT_SECONDS = int(os.getenv("OCR_TIMEOUT_SECONDS", "120"))
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

    # Image enhancement (OpenCV) — binarize only helps Tesseract on clean scans
    IMAGE_ENHANCE_BINARIZE = os.getenv("IMAGE_ENHANCE_BINARIZE", "false").lower() == "true"
