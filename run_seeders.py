from app import create_app
from app.db_bootstrap import ensure_database
from app.extensions import db
from app.seeders.platform_seeder import seed_all

ensure_database()
app = create_app()

with app.app_context():
  db.create_all()
  seed_all()
