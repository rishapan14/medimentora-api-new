"""Multi-file medical report upload service.

Handles batch uploads of PDFs and images, persists Report rows,
and returns a structured batch result. OCR/analysis happen in later modules.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.constants import REPORT_TYPE_IMAGE, REPORT_TYPE_PDF
from app.extensions import db
from app.models.report_model import Report
from app.services.validators import MultiUploadValidator, ValidatedUpload
from app.utils import utc_now

logger = logging.getLogger(__name__)


@dataclass
class UploadedFileResult:
    """One successfully saved file in a batch."""

    report_id: int
    original_filename: str
    file_type: str
    file_size: int
    file_path: str
    status: str = "uploaded"
    page_count: int | None = None

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "file_path": self.file_path,
            "status": self.status,
            "page_count": self.page_count,
        }


@dataclass
class BatchUploadResult:
    """Outcome of a multi-file upload."""

    success: bool
    batch_id: str
    files: list[UploadedFileResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files_received: int = 0
    files_saved: int = 0
    total_size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "batch_id": self.batch_id,
            "files_received": self.files_received,
            "files_saved": self.files_saved,
            "total_size_bytes": self.total_size_bytes,
            "files": [f.to_dict() for f in self.files],
            "reports": [
                {
                    "id": f.report_id,
                    "title": f.original_filename,
                    "file_type": f.file_type,
                    "file_path": f.file_path,
                    "status": f.status,
                    "original_filename": f.original_filename,
                    "file_size": f.file_size,
                    "page_count": f.page_count,
                    "batch_id": self.batch_id,
                }
                for f in self.files
            ],
            "errors": self.errors,
        }


class UploadService:
    """Persist one or many medical report files for a user."""

    @classmethod
    def upload_batch(
        cls,
        user_id: int,
        files: list[FileStorage],
        title: str | None = None,
    ) -> BatchUploadResult:
        """Validate and save multiple files as one upload batch."""
        batch_id = uuid.uuid4().hex
        max_files = int(cls._config("UPLOAD_MAX_FILES", 20))
        max_total = int(cls._config("UPLOAD_MAX_TOTAL_BYTES", 100 * 1024 * 1024))
        max_file = int(cls._config("UPLOAD_MAX_FILE_BYTES", max_total))

        validator = MultiUploadValidator(
            max_files=max_files,
            max_total_bytes=max_total,
            max_file_bytes=max_file,
        )
        validation = validator.validate(files)

        result = BatchUploadResult(
            success=False,
            batch_id=batch_id,
            files_received=len([f for f in files if f is not None]),
            total_size_bytes=validation.total_size_bytes,
        )

        if not validation.ok:
            result.errors = validation.error_messages()
            logger.warning(
                "Multi-upload rejected for user=%s batch=%s errors=%s",
                user_id,
                batch_id,
                result.errors,
            )
            return result

        upload_folder = cls._config("REPORT_UPLOAD_FOLDER", os.path.join("uploads", "reports"))
        os.makedirs(upload_folder, exist_ok=True)

        saved_paths: list[str] = []
        try:
            for index, item in enumerate(validation.files, start=1):
                saved = cls._save_validated_file(
                    user_id=user_id,
                    item=item,
                    batch_id=batch_id,
                    upload_folder=upload_folder,
                    title=title,
                    index=index,
                    total=len(validation.files),
                )
                saved_paths.append(saved.file_path)
                result.files.append(saved)

            db.session.commit()
            result.success = True
            result.files_saved = len(result.files)
            logger.info(
                "Multi-upload OK user=%s batch=%s files=%d bytes=%d",
                user_id,
                batch_id,
                result.files_saved,
                result.total_size_bytes,
            )
            return result
        except Exception:
            db.session.rollback()
            for path in saved_paths:
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except OSError:
                    pass
            logger.exception("Multi-upload failed for user=%s batch=%s", user_id, batch_id)
            result.success = False
            result.files = []
            result.files_saved = 0
            result.errors = ["Upload failed while saving files. Please try again."]
            return result

    @classmethod
    def _save_validated_file(
        cls,
        user_id: int,
        item: ValidatedUpload,
        batch_id: str,
        upload_folder: str,
        title: str | None,
        index: int,
        total: int,
    ) -> UploadedFileResult:
        unique_name = f"{uuid.uuid4().hex}.{item.extension}"
        safe_name = secure_filename(unique_name)
        file_path = os.path.join(upload_folder, safe_name)

        item.storage.stream.seek(0)
        item.storage.save(file_path)

        page_count = cls._pdf_page_count(file_path) if item.file_type == "pdf" else 1
        report_title = title or item.filename
        if total > 1 and not title:
            report_title = f"{item.filename}"
        elif title and total > 1:
            report_title = f"{title} ({index}/{total})"

        report = Report(
            user_id=user_id,
            title=report_title[:200],
            file_path=file_path,
            file_type=REPORT_TYPE_PDF if item.file_type == "pdf" else REPORT_TYPE_IMAGE,
            status="uploaded",
            batch_id=batch_id,
            original_filename=item.filename[:255],
            stored_filename=safe_name,
            file_size=item.size_bytes,
            page_count=page_count,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.session.add(report)
        db.session.flush()  # assign id without committing yet

        return UploadedFileResult(
            report_id=report.id,
            original_filename=item.filename,
            file_type=report.file_type,
            file_size=item.size_bytes,
            file_path=file_path,
            status=report.status,
            page_count=page_count,
        )

    @staticmethod
    def _pdf_page_count(file_path: str) -> int | None:
        try:
            import fitz

            doc = fitz.open(file_path)
            try:
                return int(doc.page_count)
            finally:
                doc.close()
        except Exception:
            return None

    @staticmethod
    def _config(key: str, default):
        try:
            return current_app.config.get(key, default)
        except RuntimeError:
            return default
