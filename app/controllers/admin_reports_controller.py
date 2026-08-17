"""Admin APIs for platform Reports (Module 10)."""

from __future__ import annotations

from flask import Response

from app.helpers.response import success_response
from app.services.admin.reports_admin_service import AdminReportsService


def admin_reports_overview():
  """GET /api/admin/reports/overview"""
  payload = AdminReportsService.overview()
  return success_response("Platform report overview retrieved.", payload)


def admin_export_users_csv():
  """GET /api/admin/reports/export/users.csv"""
  csv_text = AdminReportsService.export_users_csv()
  return Response(
    csv_text,
    mimetype="text/csv",
    headers={
      "Content-Disposition": 'attachment; filename="medimentora-users.csv"',
      "X-MediMentora-Export": "admin-users",
    },
  )


def admin_export_overview_csv():
  """GET /api/admin/reports/export/overview.csv"""
  csv_text = AdminReportsService.export_overview_csv()
  return Response(
    csv_text,
    mimetype="text/csv",
    headers={
      "Content-Disposition": 'attachment; filename="medimentora-platform-overview.csv"',
      "X-MediMentora-Export": "admin-overview",
    },
  )
