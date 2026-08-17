"""Idempotent starter content for features that require published records."""

from app.extensions import db
from app.models.quiz_model import Question, Quiz
from app.models.simulation_model import Simulation


def ensure_default_feature_content() -> list[str]:
  """Create production-safe starter content when a new database is empty."""
  created = []

  published_quiz = Quiz.query.filter_by(is_published=True, quiz_type="general").first()
  if not published_quiz:
    quiz = Quiz(
      title="Essential Clinical Knowledge",
      description="A short assessment covering core clinical observations and safety.",
      difficulty="easy",
      speciality="Nursing Fundamentals",
      time_limit_minutes=10,
      passing_score=70,
      is_published=True,
      quiz_type="general",
    )
    db.session.add(quiz)
    db.session.flush()
    db.session.add_all([
      Question(
        quiz_id=quiz.id,
        question_text="What is the normal adult resting heart rate range?",
        options=["40-60 bpm", "60-100 bpm", "100-140 bpm", "140-180 bpm"],
        correct_answer="60-100 bpm",
        explanation="A typical adult resting heart rate is 60-100 beats per minute.",
        order_index=1,
      ),
      Question(
        quiz_id=quiz.id,
        question_text="Which vital sign is measured in mmHg?",
        options=["Temperature", "Blood pressure", "Respiratory rate", "Pulse"],
        correct_answer="Blood pressure",
        explanation="Blood pressure is documented in millimetres of mercury (mmHg).",
        order_index=2,
      ),
      Question(
        quiz_id=quiz.id,
        question_text="What is the first action before direct patient contact?",
        options=["Document findings", "Perform hand hygiene", "Call the pharmacy", "Offer food"],
        correct_answer="Perform hand hygiene",
        explanation="Hand hygiene is a primary measure for preventing healthcare-associated infection.",
        order_index=3,
      ),
    ])
    created.append("quiz")

  active_simulation = Simulation.query.filter_by(is_active=True).first()
  if not active_simulation:
    db.session.add(Simulation(
      title="Hyperglycemia Initial Management",
      scenario=(
        "A 62-year-old patient with type 2 diabetes presents with polyuria, "
        "polydipsia, dry mucous membranes, and a blood glucose of 380 mg/dL."
      ),
      patient_data={
        "name": "Clinical training patient",
        "age": 62,
        "gender": "Male",
        "history": "Type 2 diabetes mellitus",
        "vitals": [
          {"label": "Glucose", "value": "380 mg/dL", "status": "abnormal"},
          {"label": "Heart rate", "value": "108 bpm", "status": "abnormal"},
          {"label": "Blood pressure", "value": "104/68 mmHg", "status": "abnormal"},
        ],
      },
      correct_diagnosis="Hyperglycemic crisis",
      correct_treatment="IV fluids and insulin",
      diagnosis_options=["Hypoglycemia", "Hyperglycemic crisis", "Urinary tract infection", "Stroke"],
      treatment_options=["Oral glucose", "IV fluids and insulin", "Antibiotics only", "Observation only"],
      difficulty="medium",
      speciality="Endocrinology",
      max_score=100,
      is_active=True,
    ))
    created.append("simulation")

  if created:
    db.session.commit()
  return created
