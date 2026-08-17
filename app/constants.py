"""Application-wide constants."""

# User roles
# Admin panel access is binary: Admin vs non-admin (User).
# Existing clinical roles remain for LMS / profession mapping.
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_DOCTOR = "doctor"
ROLE_NURSE = "nurse"
ROLE_MEDICAL_STUDENT = "medical_student"

VALID_ROLES = [
  ROLE_ADMIN,
  ROLE_USER,
  ROLE_DOCTOR,
  ROLE_NURSE,
  ROLE_MEDICAL_STUDENT,
]

# Only admins may access /admin UI and admin APIs
ADMIN_PANEL_ROLES = (ROLE_ADMIN,)


def is_admin_role(role: str | None) -> bool:
  """Return True if the role may access the Admin Panel."""
  return (role or "").strip().lower() == ROLE_ADMIN

# Report file types
REPORT_TYPE_PDF = "pdf"
REPORT_TYPE_IMAGE = "image"

# Notification types
NOTIF_LEARNING_REMINDER = "learning_reminder"
NOTIF_QUIZ_REMINDER = "quiz_reminder"
NOTIF_CERTIFICATE = "certificate_notification"

# Difficulty levels
DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"

VALID_DIFFICULTIES = [DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD]

# LMS difficulty labels (API can accept either style)
LMS_DIFFICULTY_BEGINNER = "beginner"
LMS_DIFFICULTY_INTERMEDIATE = "intermediate"
LMS_DIFFICULTY_ADVANCED = "advanced"
VALID_LMS_DIFFICULTIES = [
  DIFFICULTY_EASY,
  DIFFICULTY_MEDIUM,
  DIFFICULTY_HARD,
  LMS_DIFFICULTY_BEGINNER,
  LMS_DIFFICULTY_INTERMEDIATE,
  LMS_DIFFICULTY_ADVANCED,
]

# Medical learning categories for the LMS catalog
MEDICAL_COURSE_CATEGORIES = [
  "Anatomy",
  "Physiology",
  "Pathology",
  "Pharmacology",
  "Medical Terminology",
  "Nursing Fundamentals",
  "Clinical Skills",
  "Medical Ethics",
  "First Aid",
  "Emergency Medicine",
  "Cardiology",
  "Neurology",
  "Respiratory System",
  "Gastroenterology",
  "Endocrinology",
  "Pediatrics",
  "Obstetrics",
  "Gynecology",
  "Mental Health Nursing",
  "ICU Nursing",
  "Surgical Nursing",
  "Community Health Nursing",
  "Nutrition",
  "Patient Safety",
  "Infection Control",
  "Medical Imaging",
  "Laboratory Medicine",
  "Medical Report Interpretation",
  "ECG Interpretation",
  "X-Ray Interpretation",
  "Medical Case Studies",
  "Clinical Decision Making",
  "Evidence-Based Nursing",
]
