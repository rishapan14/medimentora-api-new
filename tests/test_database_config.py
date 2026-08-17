"""MYSQL_URL configuration and database startup tests."""

import pytest

from app.config import _mysql_settings


def test_mysql_url_populates_database_settings():
  settings = _mysql_settings(
    "mysql://railway:p%40ss@mysql.railway.internal:3307/railway"
  )

  assert settings == {
    "url": "mysql+pymysql://railway:p%40ss@mysql.railway.internal:3307/railway",
    "host": "mysql.railway.internal",
    "port": "3307",
    "name": "railway",
  }


def test_mysql_url_is_required(monkeypatch):
  monkeypatch.delenv("MYSQL_URL", raising=False)

  with pytest.raises(RuntimeError, match="MYSQL_URL is required"):
    _mysql_settings()


@pytest.mark.parametrize(
  ("mysql_url", "message"),
  (
    ("postgresql://user:pass@host/database", "mysql:// scheme"),
    ("mysql://user:pass@host", "host and database name"),
    ("not a url", "MYSQL_URL is invalid"),
  ),
)
def test_mysql_url_rejects_invalid_connections(mysql_url, message):
  with pytest.raises(RuntimeError, match=message):
    _mysql_settings(mysql_url)


def test_legacy_database_variables_cannot_override_mysql_url(monkeypatch):
  monkeypatch.setenv("MYSQL_URL", "mysql://railway:pass@mysql.internal/railway")
  monkeypatch.setenv("DATABASE_URL", "mysql://wrong:wrong@wrong-host/wrong-db")
  monkeypatch.setenv("DB_NAME", "clinical_platform_db")

  settings = _mysql_settings()

  assert settings["host"] == "mysql.internal"
  assert settings["name"] == "railway"


def test_database_bootstrap_connects_with_mysql_url(monkeypatch):
  from app import db_bootstrap

  calls = []

  class Connection:
    def __enter__(self):
      calls.append("entered")
      return self

    def __exit__(self, *_args):
      calls.append("exited")

    def execute(self, statement):
      calls.append(str(statement))

  class Engine:
    def connect(self):
      calls.append("connect")
      return Connection()

    def dispose(self):
      calls.append("disposed")

  def create_engine(url, **options):
    calls.append((url, options))
    return Engine()

  monkeypatch.setattr(db_bootstrap, "create_engine", create_engine)
  monkeypatch.setattr(
    db_bootstrap.Config,
    "MYSQL_URL",
    "mysql+pymysql://railway:pass@mysql.internal/railway",
  )
  monkeypatch.setattr(db_bootstrap.Config, "MYSQL_HOST", "mysql.internal")
  monkeypatch.setattr(db_bootstrap.Config, "MYSQL_PORT", "3306")
  monkeypatch.setattr(db_bootstrap.Config, "MYSQL_DATABASE", "railway")

  db_bootstrap.ensure_database()

  assert calls[0] == (
    "mysql+pymysql://railway:pass@mysql.internal/railway",
    {"pool_pre_ping": True, "connect_args": {"connect_timeout": 10}},
  )
  assert "SELECT 1" in calls
  assert calls[-1] == "disposed"
