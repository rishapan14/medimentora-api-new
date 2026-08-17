"""Phase 17 — educational model evaluation metrics."""

from __future__ import annotations

from app.services.xray.evaluation import EVALUATION_VERSION, SAFETY, XrayModelEvaluationService


def test_evaluation_report_empty_safety(app_ctx):
  report = XrayModelEvaluationService.build_report(status="completed", limit_rows=10)
  assert report["success"] is True
  assert report["evaluation_version"] == EVALUATION_VERSION
  assert report["sample_size"] >= 0
  assert report["safety"]["educational_monitoring_only"] is True
  assert report["safety"]["not_clinical_performance"] is True
  assert report["safety"]["not_accuracy_precision_recall"] is True
  assert report["safety"]["gold_standard_required_for_clinical_claims"] is True
  assert "provenance" in report
  assert "confidence" in report
  assert "findings" in report
  assert "detection_agreement" in report


def test_evaluation_aggregates_fixture_rows(app_ctx, tmp_path):
  from app.extensions import db
  from app.models.user_model import User
  from app.models.xray_analysis_model import XRAY_STATUS_COMPLETED, XrayAnalysis

  user = User.query.filter_by(email="student@clinical.com").first()
  assert user is not None

  fake = tmp_path / "eval_phase17.png"
  fake.write_bytes(b"\x89PNG\r\n\x1a\nfake")

  row = XrayAnalysis(
    user_id=user.id,
    filename="eval_phase17.png",
    stored_filename="eval_phase17.png",
    file_path=str(fake),
    file_type="png",
    file_size=fake.stat().st_size,
    body_part="Chest",
    status=XRAY_STATUS_COMPLETED,
    confidence=0.82,
    model_name="chest-specialist",
    analysis_version="1.0.0",
    model_routing={
      "specialist_key": "chest",
      "fallback_used": False,
      "model_name": "chest-specialist",
    },
    body_detection={"body_part": "Chest", "agrees_with_declared": True},
    projection_detection={"projection": "PA", "agrees_with_declared": True},
    image_quality={"quality_score": 88, "is_poor": False},
    possible_findings=[{"label": "Possible Lung Opacity", "probability": 0.7}],
    structured_findings={"findings": [{"label": "Possible Lung Opacity", "probability": 0.7}]},
    ensemble_result={"agreement": {"findings_overlap_ratio": 0.5}},
  )
  db.session.add(row)
  db.session.commit()
  xray_id = row.id

  report = XrayModelEvaluationService.build_report(
    model_name="chest-specialist",
    status="completed",
    limit_rows=500,
  )
  assert report["sample_size"] >= 1
  assert report["provenance"]["by_model_name"].get("chest-specialist", 0) >= 1
  assert report["provenance"]["by_specialist_key"].get("chest", 0) >= 1
  assert report["confidence"]["mean"] is not None
  assert any(
    f["label"] == "Possible Lung Opacity" for f in report["findings"]["top_labels"]
  )
  assert report["detection_agreement"]["body_part"]["agree"] >= 1

  # cleanup
  db.session.delete(db.session.get(XrayAnalysis, xray_id))
  db.session.commit()


def test_admin_evaluation_metrics_api(client, admin_auth_headers):
  resp = client.get(
    "/api/admin/xray-analyses/evaluation-metrics?status=completed&limit_rows=50",
    headers=admin_auth_headers,
  )
  assert resp.status_code == 200
  evaluation = resp.get_json()["data"]["evaluation"]
  assert evaluation["safety"]["not_clinical_performance"] is True
  assert evaluation["evaluation_version"] == EVALUATION_VERSION
  assert "sample_size" in evaluation


def test_admin_evaluation_requires_admin(client, auth_headers):
  resp = client.get(
    "/api/admin/xray-analyses/evaluation-metrics",
    headers=auth_headers,
  )
  assert resp.status_code in (401, 403)


def test_safety_constant_shape():
  assert SAFETY["educational_monitoring_only"] is True
  assert "gold_standard" in SAFETY["note"].lower() or SAFETY["gold_standard_required_for_clinical_claims"]
