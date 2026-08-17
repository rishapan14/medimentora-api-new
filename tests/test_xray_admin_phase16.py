"""Phase 16 — admin X-ray analysis monitor enrichments."""

from __future__ import annotations


def test_admin_stats_include_with_heatmap(client, admin_auth_headers):
  resp = client.get("/api/admin/xray-analyses?limit=5", headers=admin_auth_headers)
  assert resp.status_code == 200
  stats = resp.get_json()["data"]["stats"]
  assert "with_heatmap" in stats
  assert "failed" in stats
  assert "completed" in stats
  assert "with_comparison" in stats


def test_admin_list_row_phase16_fields(client, admin_auth_headers, app_ctx, tmp_path):
  from app.extensions import db
  from app.models.user_model import User
  from app.models.xray_analysis_model import XRAY_STATUS_COMPLETED, XrayAnalysis

  user = User.query.filter_by(email="student@clinical.com").first()
  assert user is not None

  fake_file = tmp_path / "admin_phase16_chest.png"
  fake_file.write_bytes(b"\x89PNG\r\n\x1a\nfake")
  heat = tmp_path / "admin_phase16_heatmap.png"
  heat.write_bytes(b"heat")

  row = XrayAnalysis(
    user_id=user.id,
    filename="admin_phase16_chest.png",
    stored_filename="admin_phase16_chest.png",
    file_path=str(fake_file),
    file_type="png",
    file_size=fake_file.stat().st_size,
    body_part="Chest",
    patient_age=50,
    gender="Female",
    clinical_extras={"projection": "PA"},
    status=XRAY_STATUS_COMPLETED,
    confidence=0.7,
    heatmap_path=str(heat),
    heatmap_meta={"method": "gradcam_proxy"},
    image_quality={"quality_score": 82, "grade": "good", "is_poor": False},
    body_detection={"body_part": "Chest", "confidence": 0.9},
    projection_detection={"projection": "PA", "confidence": 0.8},
    structured_findings={
      "findings": [{"label": "Possible Lung Opacity", "probability": 0.66}],
      "abnormality_score": 0.66,
    },
    possible_findings=[{"label": "Possible Lung Opacity", "probability": 0.66}],
    model_name="test-model",
  )
  db.session.add(row)
  db.session.commit()
  xray_id = row.id

  listed = client.get(
    "/api/admin/xray-analyses?q=admin_phase16&has_heatmap=true",
    headers=admin_auth_headers,
  )
  assert listed.status_code == 200
  analyses = listed.get_json()["data"]["analyses"]
  match = next((a for a in analyses if a["id"] == xray_id), None)
  assert match is not None
  assert match["has_heatmap"] is True
  assert match["projection"] == "PA"
  assert match["image_quality_score"] == 82
  assert match["has_structured_findings"] is True
  assert match["detected_body_part"] == "Chest"

  detail = client.get(
    f"/api/admin/xray-analyses/{xray_id}",
    headers=admin_auth_headers,
  )
  assert detail.status_code == 200
  body = detail.get_json()["data"]["analysis"]
  assert body["has_heatmap"] is True
  assert body["image_quality"]["quality_score"] == 82
  assert body["structured_findings"]["findings"]

  deleted = client.delete(
    f"/api/admin/xray-analyses/{xray_id}",
    headers=admin_auth_headers,
  )
  assert deleted.status_code == 200
