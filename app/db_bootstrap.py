"""Wait for the database configured by MYSQL_URL before schema creation."""

import os
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Config


def ensure_database():
  """Wait until the MySQL database in MYSQL_URL is reachable."""
  attempts = int(os.getenv("DB_BOOTSTRAP_ATTEMPTS", "30"))
  delay = float(os.getenv("DB_BOOTSTRAP_RETRY_SECONDS", "2"))
  last_error = None

  for attempt in range(1, attempts + 1):
    engine = create_engine(
      Config.MYSQL_URL,
      pool_pre_ping=True,
      connect_args={"connect_timeout": 10},
    )
    try:
      with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
      print(f"[schema] MySQL database '{Config.MYSQL_DATABASE}' is reachable", flush=True)
      return
    except SQLAlchemyError as exc:
      last_error = exc
      print(
        f"[schema] MySQL unavailable at {Config.MYSQL_HOST}:{Config.MYSQL_PORT} "
        f"(attempt {attempt}/{attempts}): {exc}",
        flush=True,
      )
      if attempt < attempts:
        time.sleep(delay)
    finally:
      engine.dispose()

  raise RuntimeError(
    f"Could not connect to MySQL database '{Config.MYSQL_DATABASE}' after {attempts} attempts"
  ) from last_error
