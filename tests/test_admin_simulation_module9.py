"""Module 9 — Admin Simulations management API tests."""

from __future__ import annotations


def test_admin_simulations_requires_admin(client, auth_headers):
  resp = client.get("/api/admin/simulations", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_list_simulations_ok(client, admin_auth_headers):
  resp = client.get("/api/admin/simulations?limit=20", headers=admin_auth_headers)
  assert resp.status_code == 200
  data = resp.get_json()["data"]
  assert "simulations" in data
  assert "stats" in data
  assert "simulations" in data["stats"]


def test_admin_simulation_crud(client, admin_auth_headers, app_ctx):
  from app.extensions import db
  from app.models.simulation_model import Simulation

  create = client.post(
    "/api/admin/simulations",
    json={
      "title": "Admin Module 9 Chest Pain Case",
      "scenario": "45-year-old with acute chest pain radiating to the left arm.",
      "correct_diagnosis": "Acute coronary syndrome",
      "correct_treatment": "Aspirin + urgent ECG + cardiology consult",
      "diagnosis_options": [
        "Acute coronary syndrome",
        "GERD",
        "Musculoskeletal pain",
        "Pneumonia",
      ],
      "treatment_options": [
        "Aspirin + urgent ECG + cardiology consult",
        "Antacids and discharge",
        "Antibiotics only",
      ],
      "difficulty": "medium",
      "speciality": "Emergency Medicine",
      "max_score": 100,
      "is_active": False,
      "patient_data": {"age": 45, "sex": "Male"},
    },
    headers=admin_auth_headers,
  )
  assert create.status_code == 201
  sim = create.get_json()["data"]["simulation"]
  sim_id = sim["id"]
  assert sim["is_active"] is False
  assert sim["correct_diagnosis"] == "Acute coronary syndrome"

  activate = client.post(
    f"/api/admin/simulations/{sim_id}/status",
    json={"is_active": True},
    headers=admin_auth_headers,
  )
  assert activate.status_code == 200
  assert activate.get_json()["data"]["simulation"]["is_active"] is True

  detail = client.get(
    f"/api/admin/simulations/{sim_id}",
    headers=admin_auth_headers,
  )
  assert detail.status_code == 200
  assert "correct_treatment" in detail.get_json()["data"]["simulation"]

  bad = client.post(
    "/api/admin/simulations",
    json={
      "title": "Bad sim",
      "scenario": "x",
      "correct_diagnosis": "Not in list",
      "correct_treatment": "Aspirin + urgent ECG + cardiology consult",
      "diagnosis_options": ["GERD", "Pneumonia"],
      "treatment_options": ["Aspirin + urgent ECG + cardiology consult"],
    },
    headers=admin_auth_headers,
  )
  assert bad.status_code == 400

  deleted = client.delete(
    f"/api/admin/simulations/{sim_id}",
    headers=admin_auth_headers,
  )
  assert deleted.status_code == 200
  assert db.session.get(Simulation, sim_id) is None


def test_admin_create_simulation_validation(client, admin_auth_headers):
  resp = client.post(
    "/api/admin/simulations",
    json={"title": "Incomplete"},
    headers=admin_auth_headers,
  )
  assert resp.status_code == 400
