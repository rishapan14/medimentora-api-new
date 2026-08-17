"""Admin Panel API services."""

from app.services.admin.learning_admin_service import AdminLearningService
from app.services.admin.quiz_admin_service import AdminQuizService
from app.services.admin.report_analysis_admin_service import AdminReportAnalysisService
from app.services.admin.reports_admin_service import AdminReportsService
from app.services.admin.settings_admin_service import AdminSettingsService
from app.services.admin.simulation_admin_service import AdminSimulationService
from app.services.admin.user_admin_service import AdminUserService
from app.services.admin.xray_analysis_admin_service import AdminXrayAnalysisService

__all__ = [
  "AdminUserService",
  "AdminReportAnalysisService",
  "AdminXrayAnalysisService",
  "AdminLearningService",
  "AdminQuizService",
  "AdminSimulationService",
  "AdminReportsService",
  "AdminSettingsService",
]
