"""Database-backed worker for AI Medical Teacher document jobs."""

from __future__ import annotations

import logging
import signal
import time

from app import create_app
from app.helpers.schema_patches import ensure_medical_teacher_schema
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
_running = True


def _stop(_signum, _frame):
  global _running
  _running = False


def main() -> None:
  signal.signal(signal.SIGTERM, _stop)
  signal.signal(signal.SIGINT, _stop)
  app = create_app()
  poll_seconds = max(0.25, float(app.config.get("TEACHER_JOB_POLL_SECONDS", 2)))
  logger.info("Learning document worker started (poll=%ss)", poll_seconds)

  with app.app_context():
    ensure_medical_teacher_schema()
    while _running:
      try:
        job = DocumentProcessingJobService.claim_next()
        if job:
          logger.info("Processing learning document job %s", job.public_id)
          DocumentProcessingJobService.process_claimed(job)
          continue
      except Exception:
        logger.exception("Learning document worker iteration failed")
      time.sleep(poll_seconds)

  logger.info("Learning document worker stopped")


if __name__ == "__main__":
  main()
