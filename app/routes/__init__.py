from app.docs import docs_bp
from app.routes.auth_routes import auth_bp
from app.routes.report_routes import report_bp
from app.routes.analysis_routes import analysis_bp
from app.routes.learning_routes import learning_bp
from app.routes.clinical_case_routes import clinical_case_bp
from app.routes.simulation_routes import simulation_bp
from app.routes.quiz_routes import quiz_bp
from app.routes.progress_routes import progress_bp
from app.routes.certificate_routes import certificate_bp
from app.routes.discussion_routes import discussion_bp
from app.routes.notification_routes import notification_bp
from app.routes.medical_teacher_routes import medical_teacher_bp
from app.routes.xray_routes import xray_bp
from app.routes.admin_routes import admin_bp
from app.routes.platform_routes import platform_bp


def register_blueprints(app):
  """Register all API blueprints."""
  app.register_blueprint(docs_bp)
  app.register_blueprint(auth_bp)
  app.register_blueprint(platform_bp)
  app.register_blueprint(report_bp)
  app.register_blueprint(analysis_bp)
  app.register_blueprint(learning_bp)
  app.register_blueprint(clinical_case_bp)
  app.register_blueprint(simulation_bp)
  app.register_blueprint(quiz_bp)
  app.register_blueprint(progress_bp)
  app.register_blueprint(certificate_bp)
  app.register_blueprint(discussion_bp)
  app.register_blueprint(notification_bp)
  app.register_blueprint(medical_teacher_bp)
  app.register_blueprint(xray_bp)
  app.register_blueprint(admin_bp)
