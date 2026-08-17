"""Seed demo data for development and testing."""

from app.extensions import db
from app.models.course_model import Course, Lesson
from app.models.clinical_case_model import ClinicalCase
from app.models.quiz_model import Question, Quiz
from app.models.simulation_model import Simulation
from app.models.user_model import User
from app.constants import ROLE_ADMIN, ROLE_DOCTOR, ROLE_NURSE, ROLE_MEDICAL_STUDENT


def seed_clinical_cases_if_needed():
  """Add demo clinical cases when the library is empty or incomplete."""
  if ClinicalCase.query.count() >= 4:
    return

  doctor = User.query.filter_by(email="doctor@clinical.com").first()
  nurse = User.query.filter_by(email="nurse@clinical.com").first()
  creator = doctor or nurse or User.query.first()
  if not creator:
    return

  existing_titles = {c.title for c in ClinicalCase.query.all()}
  candidates = [
    ClinicalCase(
      created_by=creator.id,
      title="Chest Pain in a 55-year-old Male",
      disease="Acute Coronary Syndrome",
      symptoms=["Chest pain", "Shortness of breath", "Diaphoresis"],
      diagnosis="STEMI suspected based on ECG changes",
      treatment="Aspirin, nitroglycerin, urgent cardiology referral",
      difficulty="medium",
      speciality="Cardiology",
      description="Patient presents with crushing chest pain radiating to left arm.",
    ),
    ClinicalCase(
      created_by=creator.id,
      title="Sudden Weakness in a 68-year-old Female",
      disease="Ischemic Stroke",
      symptoms=["Facial droop", "Arm weakness", "Slurred speech"],
      diagnosis="Acute ischemic stroke, NIHSS 8",
      treatment="tPA eligibility assessment, stroke unit admission, aspirin after bleed ruled out",
      difficulty="hard",
      speciality="Neurology",
      description="Patient presents with sudden onset left-sided weakness and aphasia.",
    ),
    ClinicalCase(
      created_by=creator.id,
      title="Post-operative Wound Care",
      disease="Surgical Site Infection",
      symptoms=["Erythema", "Purulent drainage", "Fever"],
      diagnosis="Superficial surgical site infection",
      treatment="Wound culture, antibiotics, dressing changes, monitor vitals",
      difficulty="easy",
      speciality="Nursing Fundamentals",
      description="Day 4 post-appendectomy patient with increasing wound erythema and low-grade fever.",
    ),
    ClinicalCase(
      created_by=creator.id,
      title="Pediatric Fever and Rash",
      disease="Viral Exanthem",
      symptoms=["Fever", "Maculopapular rash", "Irritability"],
      diagnosis="Likely viral illness; measles ruled out by vaccination history",
      treatment="Supportive care, antipyretics, hydration, isolation precautions as needed",
      difficulty="medium",
      speciality="Pediatrics",
      description="3-year-old with 2 days of fever followed by spreading rash.",
    ),
  ]

  added = [c for c in candidates if c.title not in existing_titles]
  if not added:
    return

  db.session.add_all(added)
  db.session.commit()
  print(f"Added {len(added)} clinical case(s).")


def seed_all():
  if User.query.filter_by(email="admin@clinical.com").first():
    print("Seed data already exists. Skipping.")
    seed_clinical_cases_if_needed()
    return

  # Users
  admin = User(email="admin@clinical.com", full_name="System Admin", role=ROLE_ADMIN)
  admin.set_password("admin123")

  doctor = User(email="doctor@clinical.com", full_name="Dr. Sarah Chen", role=ROLE_DOCTOR, speciality="Cardiology")
  doctor.set_password("doctor123")

  nurse = User(email="nurse@clinical.com", full_name="Nurse Emily", role=ROLE_NURSE, speciality="General Nursing")
  nurse.set_password("nurse123")

  student = User(email="student@clinical.com", full_name="Alex Student", role=ROLE_MEDICAL_STUDENT)
  student.set_password("student123")

  db.session.add_all([admin, doctor, nurse, student])
  db.session.flush()

  # Course & lessons
  course = Course(
    title="Fundamentals of Clinical Nursing",
    description="Core nursing concepts for beginners.",
    speciality="Nursing Fundamentals",
    difficulty="beginner",
    duration_hours=10,
    instructor_name="Nurse Emily",
    is_published=True,
    certificate_eligible=True,
  )
  db.session.add(course)
  db.session.flush()

  lessons = [
    Lesson(course_id=course.id, title="Vital Signs Assessment", content="Learn to measure BP, pulse, respiration, temperature.", order_index=1),
    Lesson(course_id=course.id, title="CBC Interpretation", content="Understanding complete blood count results.", order_index=2),
    Lesson(course_id=course.id, title="Medication Administration", content="Safe medication practices for nurses.", order_index=3),
  ]
  db.session.add_all(lessons)

  # Clinical case
  case = ClinicalCase(
    created_by=doctor.id,
    title="Chest Pain in a 55-year-old Male",
    disease="Acute Coronary Syndrome",
    symptoms=["Chest pain", "Shortness of breath", "Diaphoresis"],
    diagnosis="STEMI suspected based on ECG changes",
    treatment="Aspirin, nitroglycerin, urgent cardiology referral",
    difficulty="medium",
    speciality="Cardiology",
    description="Patient presents with crushing chest pain radiating to left arm.",
  )
  db.session.add(case)

  extra_cases = [
    ClinicalCase(
      created_by=doctor.id,
      title="Sudden Weakness in a 68-year-old Female",
      disease="Ischemic Stroke",
      symptoms=["Facial droop", "Arm weakness", "Slurred speech"],
      diagnosis="Acute ischemic stroke, NIHSS 8",
      treatment="tPA eligibility assessment, stroke unit admission, aspirin after bleed ruled out",
      difficulty="hard",
      speciality="Neurology",
      description="Patient presents with sudden onset left-sided weakness and aphasia.",
    ),
    ClinicalCase(
      created_by=nurse.id,
      title="Post-operative Wound Care",
      disease="Surgical Site Infection",
      symptoms=["Erythema", "Purulent drainage", "Fever"],
      diagnosis="Superficial surgical site infection",
      treatment="Wound culture, antibiotics, dressing changes, monitor vitals",
      difficulty="easy",
      speciality="Nursing Fundamentals",
      description="Day 4 post-appendectomy patient with increasing wound erythema and low-grade fever.",
    ),
    ClinicalCase(
      created_by=doctor.id,
      title="Pediatric Fever and Rash",
      disease="Viral Exanthem",
      symptoms=["Fever", "Maculopapular rash", "Irritability"],
      diagnosis="Likely viral illness; measles ruled out by vaccination history",
      treatment="Supportive care, antipyretics, hydration, isolation precautions as needed",
      difficulty="medium",
      speciality="Pediatrics",
      description="3-year-old with 2 days of fever followed by spreading rash.",
    ),
  ]
  db.session.add_all(extra_cases)

  # Quiz
  quiz = Quiz(
    title="Nursing Fundamentals Quiz",
    description="Test your basic nursing knowledge.",
    difficulty="easy",
    speciality="Nursing Fundamentals",
    created_by=doctor.id,
  )
  db.session.add(quiz)
  db.session.flush()

  questions = [
    Question(
      quiz_id=quiz.id,
      question_text="What is the normal adult resting heart rate range?",
      options=["40-60 bpm", "60-100 bpm", "100-140 bpm", "140-180 bpm"],
      correct_answer="60-100 bpm",
      explanation="Normal resting heart rate for adults is 60-100 beats per minute.",
    ),
    Question(
      quiz_id=quiz.id,
      question_text="Which vital sign is measured in mmHg?",
      options=["Temperature", "Blood Pressure", "Respiratory Rate", "Pulse"],
      correct_answer="Blood Pressure",
    ),
  ]
  db.session.add_all(questions)

  # Simulation
  sim = Simulation(
    title="Diabetic Patient with Hyperglycemia",
    scenario="A 62-year-old diabetic patient presents with polyuria, polydipsia, and blood glucose of 380 mg/dL.",
    patient_data={
      "age": 62,
      "gender": "Male",
      "glucose": 380,
      "history": "Type 2 Diabetes",
      "vitals": [
        {"label": "Glucose", "value": "380 mg/dL", "status": "abnormal"},
        {"label": "Age", "value": "62 years", "status": "normal"},
      ],
    },
    correct_diagnosis="Hyperglycemic crisis",
    correct_treatment="IV fluids and insulin",
    diagnosis_options=["Hypoglycemia", "Hyperglycemic crisis", "DKA only", "UTI"],
    treatment_options=["Oral glucose", "IV fluids and insulin", "Antibiotics only", "Observation"],
    difficulty="medium",
    speciality="Endocrinology",
  )
  db.session.add(sim)

  db.session.commit()
  print("Seed data created successfully.")
  print("Demo accounts: admin@clinical.com / admin123, student@clinical.com / student123")
