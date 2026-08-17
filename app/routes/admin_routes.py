"""Admin Panel API routes — JWT + admin role required."""

from flask import Blueprint

from app.controllers import admin_learning_controller as learning_ctrl
from app.controllers import admin_quiz_controller as quiz_ctrl
from app.controllers import admin_report_analysis_controller as reports_ctrl
from app.controllers import admin_reports_controller as platform_reports_ctrl
from app.controllers import admin_settings_controller as settings_ctrl
from app.controllers import admin_simulation_controller as sim_ctrl
from app.controllers import admin_user_controller as users_ctrl
from app.controllers import admin_xray_analysis_controller as xray_ctrl
from app.middleware import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

admin_bp.add_url_rule(
  "/users",
  view_func=admin_required(users_ctrl.admin_list_users),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/users/<int:user_id>",
  view_func=admin_required(users_ctrl.admin_get_user),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/users/<int:user_id>/role",
  view_func=admin_required(users_ctrl.admin_update_user_role),
  methods=["PATCH", "PUT"],
)
admin_bp.add_url_rule(
  "/users/<int:user_id>/status",
  view_func=admin_required(users_ctrl.admin_set_user_active),
  methods=["POST", "PATCH"],
)

# Module 5 — AI Report Analysis monitoring
admin_bp.add_url_rule(
  "/report-analyses",
  view_func=admin_required(reports_ctrl.admin_list_report_analyses),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/report-analyses/<int:analysis_id>",
  view_func=admin_required(reports_ctrl.admin_get_report_analysis),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/report-analyses/<int:analysis_id>",
  view_func=admin_required(reports_ctrl.admin_delete_report_analysis),
  methods=["DELETE"],
  endpoint="admin_delete_report_analysis",
)

# Module 6 / Phase 16–17 — AI X-Ray Analysis monitoring + educational model evaluation
admin_bp.add_url_rule(
  "/xray-analyses/evaluation-metrics",
  view_func=admin_required(xray_ctrl.admin_xray_evaluation_metrics),
  methods=["GET"],
  endpoint="admin_xray_evaluation_metrics",
)
admin_bp.add_url_rule(
  "/xray-analyses",
  view_func=admin_required(xray_ctrl.admin_list_xray_analyses),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/xray-analyses/<int:xray_id>",
  view_func=admin_required(xray_ctrl.admin_get_xray_analysis),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/xray-analyses/<int:xray_id>",
  view_func=admin_required(xray_ctrl.admin_delete_xray_analysis),
  methods=["DELETE"],
  endpoint="admin_delete_xray_analysis",
)

# Module 7 — Learning Content management
admin_bp.add_url_rule(
  "/learning/categories",
  view_func=admin_required(learning_ctrl.admin_list_categories),
  methods=["GET"],
)

# Phase 2 — Body Systems Learning Hub admin
from app.controllers import admin_body_system_controller as hub_admin_ctrl

admin_bp.add_url_rule(
  "/learning/body-systems",
  view_func=admin_required(hub_admin_ctrl.admin_list_body_systems),
  methods=["GET"],
  endpoint="admin_list_body_systems",
)
admin_bp.add_url_rule(
  "/learning/body-systems",
  view_func=admin_required(hub_admin_ctrl.admin_create_body_system),
  methods=["POST"],
  endpoint="admin_create_body_system",
)
admin_bp.add_url_rule(
  "/learning/body-systems/<string:slug>",
  view_func=admin_required(hub_admin_ctrl.admin_get_body_system),
  methods=["GET"],
  endpoint="admin_get_body_system",
)
admin_bp.add_url_rule(
  "/learning/body-systems/<string:slug>",
  view_func=admin_required(hub_admin_ctrl.admin_update_body_system),
  methods=["PUT", "PATCH"],
  endpoint="admin_update_body_system",
)
admin_bp.add_url_rule(
  "/learning/body-systems/<string:slug>",
  view_func=admin_required(hub_admin_ctrl.admin_delete_body_system),
  methods=["DELETE"],
  endpoint="admin_delete_body_system",
)
admin_bp.add_url_rule(
  "/learning/body-systems/<string:slug>/organs",
  view_func=admin_required(hub_admin_ctrl.admin_create_organ),
  methods=["POST"],
  endpoint="admin_create_organ",
)
admin_bp.add_url_rule(
  "/learning/organs/<string:organ_slug>",
  view_func=admin_required(hub_admin_ctrl.admin_update_organ),
  methods=["PUT", "PATCH"],
  endpoint="admin_update_organ",
)
admin_bp.add_url_rule(
  "/learning/body-systems/<string:slug>/diseases",
  view_func=admin_required(hub_admin_ctrl.admin_create_disease),
  methods=["POST"],
  endpoint="admin_create_disease",
)
admin_bp.add_url_rule(
  "/learning/body-systems/<string:slug>/courses",
  view_func=admin_required(hub_admin_ctrl.admin_link_course),
  methods=["POST"],
  endpoint="admin_link_body_system_course",
)
admin_bp.add_url_rule(
  "/learning/body-systems/<string:slug>/quizzes",
  view_func=admin_required(hub_admin_ctrl.admin_link_quiz),
  methods=["POST"],
  endpoint="admin_link_body_system_quiz",
)

admin_bp.add_url_rule(
  "/learning/courses",
  view_func=admin_required(learning_ctrl.admin_list_courses),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/learning/courses",
  view_func=admin_required(learning_ctrl.admin_create_course),
  methods=["POST"],
  endpoint="admin_create_course",
)
admin_bp.add_url_rule(
  "/learning/courses/<int:course_id>",
  view_func=admin_required(learning_ctrl.admin_get_course),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/learning/courses/<int:course_id>",
  view_func=admin_required(learning_ctrl.admin_update_course),
  methods=["PUT", "PATCH"],
  endpoint="admin_update_course",
)
admin_bp.add_url_rule(
  "/learning/courses/<int:course_id>/publish",
  view_func=admin_required(learning_ctrl.admin_set_course_published),
  methods=["POST", "PATCH"],
)
admin_bp.add_url_rule(
  "/learning/courses/<int:course_id>",
  view_func=admin_required(learning_ctrl.admin_delete_course),
  methods=["DELETE"],
  endpoint="admin_delete_course",
)
admin_bp.add_url_rule(
  "/learning/courses/<int:course_id>/lessons",
  view_func=admin_required(learning_ctrl.admin_list_lessons),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/learning/lessons",
  view_func=admin_required(learning_ctrl.admin_create_lesson),
  methods=["POST"],
)
admin_bp.add_url_rule(
  "/learning/lessons/<int:lesson_id>",
  view_func=admin_required(learning_ctrl.admin_update_lesson),
  methods=["PUT", "PATCH"],
)
admin_bp.add_url_rule(
  "/learning/lessons/<int:lesson_id>",
  view_func=admin_required(learning_ctrl.admin_delete_lesson),
  methods=["DELETE"],
  endpoint="admin_delete_lesson",
)

# Module 8 — Quiz Management
admin_bp.add_url_rule(
  "/quizzes",
  view_func=admin_required(quiz_ctrl.admin_list_quizzes),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/quizzes",
  view_func=admin_required(quiz_ctrl.admin_create_quiz),
  methods=["POST"],
  endpoint="admin_create_quiz",
)
admin_bp.add_url_rule(
  "/quizzes/<int:quiz_id>",
  view_func=admin_required(quiz_ctrl.admin_get_quiz),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/quizzes/<int:quiz_id>",
  view_func=admin_required(quiz_ctrl.admin_update_quiz),
  methods=["PUT", "PATCH"],
  endpoint="admin_update_quiz",
)
admin_bp.add_url_rule(
  "/quizzes/<int:quiz_id>/publish",
  view_func=admin_required(quiz_ctrl.admin_set_quiz_published),
  methods=["POST", "PATCH"],
)
admin_bp.add_url_rule(
  "/quizzes/<int:quiz_id>",
  view_func=admin_required(quiz_ctrl.admin_delete_quiz),
  methods=["DELETE"],
  endpoint="admin_delete_quiz",
)
admin_bp.add_url_rule(
  "/quizzes/<int:quiz_id>/questions",
  view_func=admin_required(quiz_ctrl.admin_list_questions),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/quizzes/<int:quiz_id>/questions",
  view_func=admin_required(quiz_ctrl.admin_create_question),
  methods=["POST"],
  endpoint="admin_create_question",
)
admin_bp.add_url_rule(
  "/quizzes/questions/<int:question_id>",
  view_func=admin_required(quiz_ctrl.admin_update_question),
  methods=["PUT", "PATCH"],
)
admin_bp.add_url_rule(
  "/quizzes/questions/<int:question_id>",
  view_func=admin_required(quiz_ctrl.admin_delete_question),
  methods=["DELETE"],
  endpoint="admin_delete_question",
)

# Module 9 — Simulations management
admin_bp.add_url_rule(
  "/simulations",
  view_func=admin_required(sim_ctrl.admin_list_simulations),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/simulations",
  view_func=admin_required(sim_ctrl.admin_create_simulation),
  methods=["POST"],
  endpoint="admin_create_simulation",
)
admin_bp.add_url_rule(
  "/simulations/<int:simulation_id>",
  view_func=admin_required(sim_ctrl.admin_get_simulation),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/simulations/<int:simulation_id>",
  view_func=admin_required(sim_ctrl.admin_update_simulation),
  methods=["PUT", "PATCH"],
  endpoint="admin_update_simulation",
)
admin_bp.add_url_rule(
  "/simulations/<int:simulation_id>/status",
  view_func=admin_required(sim_ctrl.admin_set_simulation_active),
  methods=["POST", "PATCH"],
)
admin_bp.add_url_rule(
  "/simulations/<int:simulation_id>",
  view_func=admin_required(sim_ctrl.admin_delete_simulation),
  methods=["DELETE"],
  endpoint="admin_delete_simulation",
)

# Module 10 — Platform Reports
admin_bp.add_url_rule(
  "/reports/overview",
  view_func=admin_required(platform_reports_ctrl.admin_reports_overview),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/reports/export/users.csv",
  view_func=admin_required(platform_reports_ctrl.admin_export_users_csv),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/reports/export/overview.csv",
  view_func=admin_required(platform_reports_ctrl.admin_export_overview_csv),
  methods=["GET"],
)

# Module 11 — Admin Settings
admin_bp.add_url_rule(
  "/settings",
  view_func=admin_required(settings_ctrl.admin_get_settings),
  methods=["GET"],
)
admin_bp.add_url_rule(
  "/settings",
  view_func=admin_required(settings_ctrl.admin_update_settings),
  methods=["PUT", "PATCH"],
  endpoint="admin_update_settings",
)
admin_bp.add_url_rule(
  "/settings/reset",
  view_func=admin_required(settings_ctrl.admin_reset_settings),
  methods=["POST"],
)
