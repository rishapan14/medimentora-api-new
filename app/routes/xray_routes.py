"""Routes for AI-Assisted X-Ray Analysis — Modules 2–3."""

from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.controllers import xray_controller as ctrl

xray_bp = Blueprint("xray", __name__, url_prefix="/api/xray")

# Module 2 — Upload + ownership-scoped history
xray_bp.add_url_rule(
  "/upload",
  view_func=jwt_required()(ctrl.upload_xrays),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/history",
  view_func=jwt_required()(ctrl.list_history),
  methods=["GET"],
)
# Module 10 — Dashboard (register before /<id> for clarity)
xray_bp.add_url_rule(
  "/dashboard",
  view_func=jwt_required()(ctrl.xray_dashboard),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/clinical-options",
  view_func=jwt_required()(ctrl.clinical_form_options),
  methods=["GET"],
)
# Educational Healthy X-Ray Comparison — Reference Library (Module 2)
xray_bp.add_url_rule(
  "/references/options",
  view_func=jwt_required()(ctrl.reference_library_options),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/references/select",
  view_func=jwt_required()(ctrl.select_reference_image),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/references",
  view_func=jwt_required()(ctrl.list_reference_images),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/references/<string:reference_id>/file",
  view_func=jwt_required()(ctrl.download_reference_image),
  methods=["GET"],
)

# Admin — Reference Library Manager (DB-driven catalog)
from app.controllers import xray_reference_admin_controller as admin_ctrl
from app.middleware import admin_required

xray_bp.add_url_rule(
  "/admin/references/options",
  view_func=admin_required(admin_ctrl.admin_options),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/admin/references/stats",
  view_func=admin_required(admin_ctrl.admin_stats),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/admin/references/sync",
  view_func=admin_required(admin_ctrl.admin_sync_from_disk),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/admin/references/bulk",
  view_func=admin_required(admin_ctrl.admin_bulk_upload),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/admin/references/bulk-zip",
  view_func=admin_required(admin_ctrl.admin_bulk_upload_zip),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/admin/references",
  view_func=admin_required(admin_ctrl.admin_list_references),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/admin/references",
  view_func=admin_required(admin_ctrl.admin_upload_reference),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/admin/references/<int:ref_id>",
  view_func=admin_required(admin_ctrl.admin_get_reference),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/admin/references/<int:ref_id>",
  view_func=admin_required(admin_ctrl.admin_update_reference),
  methods=["PATCH", "PUT"],
)
xray_bp.add_url_rule(
  "/admin/references/<int:ref_id>",
  view_func=admin_required(admin_ctrl.admin_delete_reference),
  methods=["DELETE"],
)
xray_bp.add_url_rule(
  "/admin/references/<int:ref_id>/file",
  view_func=admin_required(admin_ctrl.admin_preview_reference),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/admin/references/<int:ref_id>/deactivate",
  view_func=admin_required(admin_ctrl.admin_deactivate_reference),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/admin/references/<int:ref_id>/reactivate",
  view_func=admin_required(admin_ctrl.admin_reactivate_reference),
  methods=["POST"],
)

xray_bp.add_url_rule(
  "/<int:xray_id>",
  view_func=jwt_required()(ctrl.get_xray),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>",
  view_func=jwt_required()(ctrl.delete_xray),
  methods=["DELETE"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>/file",
  view_func=jwt_required()(ctrl.download_original),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>/export",
  view_func=jwt_required()(ctrl.export_xray),
  methods=["GET"],
)

# Module 3 — Image preprocessing
xray_bp.add_url_rule(
  "/<int:xray_id>/preprocess",
  view_func=jwt_required()(ctrl.preprocess_xray),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>/preprocessed",
  view_func=jwt_required()(ctrl.download_preprocessed),
  methods=["GET"],
)

# Module 4 — Vision model analysis
xray_bp.add_url_rule(
  "/analyze",
  view_func=jwt_required()(ctrl.analyze_xrays),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>/reanalyze",
  view_func=jwt_required()(ctrl.reanalyze_xray),
  methods=["POST"],
)

# Module 5 / Phase 12 — AI LLM explanation (structured findings only — never raw images)
xray_bp.add_url_rule(
  "/<int:xray_id>/explain",
  view_func=jwt_required()(ctrl.explain_xray),
  methods=["POST"],
)

# Module 6 — Educational attention heatmap
xray_bp.add_url_rule(
  "/<int:xray_id>/heatmap",
  view_func=jwt_required()(ctrl.generate_heatmap),
  methods=["POST"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>/heatmap",
  view_func=jwt_required()(ctrl.download_heatmap),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>/reference",
  view_func=jwt_required()(ctrl.download_reference_for_xray),
  methods=["GET"],
)

# Educational Healthy X-Ray Comparison (Module 3)
xray_bp.add_url_rule(
  "/<int:xray_id>/compare",
  view_func=jwt_required()(ctrl.get_comparison),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>/compare",
  view_func=jwt_required()(ctrl.generate_comparison),
  methods=["POST"],
)

# Module 9 / Phase 13 — Learning recommendations
xray_bp.add_url_rule(
  "/<int:xray_id>/recommendations",
  view_func=jwt_required()(ctrl.get_recommendations),
  methods=["GET"],
)
xray_bp.add_url_rule(
  "/<int:xray_id>/recommendations",
  view_func=jwt_required()(ctrl.refresh_recommendations),
  methods=["POST"],
)
