"""Upload and multi-file validation for medical report analysis.

Validates file type, size, emptiness, duplicates, and basic
PDF/image readability before files are persisted.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Iterable

from werkzeug.datastructures import FileStorage

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png"})
ALLOWED_PDF_EXTENSIONS = frozenset({"pdf"})
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_PDF_EXTENSIONS

ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
        "application/octet-stream",  # browsers sometimes send this
    }
)


@dataclass
class FileValidationIssue:
    """One validation problem for a single uploaded file."""

    filename: str
    code: str
    message: str


@dataclass
class ValidatedUpload:
    """A file that passed validation and is ready to save."""

    storage: FileStorage
    filename: str
    extension: str
    file_type: str  # pdf | image
    size_bytes: int
    content_hash: str


@dataclass
class MultiUploadValidationResult:
    """Outcome of validating a multi-file upload request."""

    ok: bool
    files: list[ValidatedUpload] = field(default_factory=list)
    errors: list[FileValidationIssue] = field(default_factory=list)
    total_size_bytes: int = 0

    def error_messages(self) -> list[str]:
        return [f"{e.filename}: {e.message}" for e in self.errors]


class MultiUploadValidator:
    """Validate one or more medical report uploads for a batch request."""

    def __init__(
        self,
        max_files: int = 20,
        max_total_bytes: int = 100 * 1024 * 1024,
        max_file_bytes: int | None = None,
    ):
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes
        self.max_file_bytes = max_file_bytes or max_total_bytes

    def validate(self, files: Iterable[FileStorage | None]) -> MultiUploadValidationResult:
        """Validate a list of Werkzeug FileStorage objects."""
        result = MultiUploadValidationResult(ok=True)
        seen_hashes: set[str] = set()
        seen_names: set[str] = set()

        raw_files = [f for f in files if f is not None]
        if not raw_files:
            result.ok = False
            result.errors.append(
                FileValidationIssue(
                    filename="(none)",
                    code="no_files",
                    message="At least one PDF or image file is required.",
                )
            )
            return result

        if len(raw_files) > self.max_files:
            result.ok = False
            result.errors.append(
                FileValidationIssue(
                    filename="(batch)",
                    code="too_many_files",
                    message=f"Maximum {self.max_files} files allowed per upload (received {len(raw_files)}).",
                )
            )
            return result

        for storage in raw_files:
            item = self._validate_one(storage, seen_hashes, seen_names)
            if isinstance(item, FileValidationIssue):
                result.errors.append(item)
                continue
            result.files.append(item)
            result.total_size_bytes += item.size_bytes

        if result.total_size_bytes > self.max_total_bytes:
            result.ok = False
            mb = self.max_total_bytes / (1024 * 1024)
            result.errors.append(
                FileValidationIssue(
                    filename="(batch)",
                    code="total_size_exceeded",
                    message=f"Total upload size exceeds the {mb:.0f} MB limit.",
                )
            )
            return result

        if result.errors:
            result.ok = False
            result.files = []
            return result

        if not result.files:
            result.ok = False
            result.errors.append(
                FileValidationIssue(
                    filename="(none)",
                    code="no_valid_files",
                    message="No valid files were found in the upload.",
                )
            )
        return result

    def _validate_one(
        self,
        storage: FileStorage,
        seen_hashes: set[str],
        seen_names: set[str],
    ) -> ValidatedUpload | FileValidationIssue:
        filename = (storage.filename or "").strip()
        if not filename:
            return FileValidationIssue("(unnamed)", "empty_filename", "File has no name.")

        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            return FileValidationIssue(
                filename,
                "unsupported_type",
                f"Unsupported format '.{extension or '?'}'. Allowed: JPG, JPEG, PNG, PDF.",
            )

        mime = (storage.mimetype or "").lower()
        if mime and mime not in ALLOWED_MIME_TYPES and not mime.startswith("image/"):
            # Soft check — some browsers send odd MIME; extension is authoritative
            logger.warning("Unexpected MIME %s for %s — continuing on extension", mime, filename)

        try:
            storage.stream.seek(0, 2)
            size = storage.stream.tell()
            storage.stream.seek(0)
        except Exception:
            size = 0

        if size <= 0:
            # Fallback: read into memory for size (small files only)
            data = storage.read()
            storage.stream.seek(0)
            size = len(data)

        if size <= 0:
            return FileValidationIssue(filename, "empty_file", "File is empty.")

        if size > self.max_file_bytes:
            mb = self.max_file_bytes / (1024 * 1024)
            return FileValidationIssue(
                filename,
                "file_too_large",
                f"File exceeds the {mb:.0f} MB per-file limit.",
            )

        content = storage.read()
        storage.stream.seek(0)
        content_hash = hashlib.sha256(content).hexdigest()

        name_key = filename.lower()
        if content_hash in seen_hashes or name_key in seen_names:
            return FileValidationIssue(
                filename,
                "duplicate_file",
                "Duplicate file detected in this upload batch.",
            )
        seen_hashes.add(content_hash)
        seen_names.add(name_key)

        file_type = "pdf" if extension == "pdf" else "image"
        readability = self._check_readable(content, extension, filename)
        if readability is not None:
            return readability

        return ValidatedUpload(
            storage=storage,
            filename=filename,
            extension=extension,
            file_type=file_type,
            size_bytes=size,
            content_hash=content_hash,
        )

    @staticmethod
    def _check_readable(content: bytes, extension: str, filename: str) -> FileValidationIssue | None:
        """Reject corrupted / password-protected PDFs and unreadable images."""
        if extension == "pdf":
            return MultiUploadValidator._check_pdf(content, filename)
        return MultiUploadValidator._check_image(content, filename)

    @staticmethod
    def _check_pdf(content: bytes, filename: str) -> FileValidationIssue | None:
        if not content.startswith(b"%PDF"):
            return FileValidationIssue(filename, "corrupted_pdf", "File does not look like a valid PDF.")

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=content, filetype="pdf")
            try:
                if doc.is_encrypted or doc.needs_pass:
                    return FileValidationIssue(
                        filename,
                        "password_protected_pdf",
                        "Password-protected PDFs are not supported. Remove the password and upload again.",
                    )
                if doc.page_count < 1:
                    return FileValidationIssue(filename, "empty_pdf", "PDF has no pages.")
                # Touch first page to catch severe corruption
                _ = doc.load_page(0)
            finally:
                doc.close()
        except Exception as exc:
            logger.warning("PDF validation failed for %s: %s", filename, exc)
            return FileValidationIssue(
                filename,
                "corrupted_pdf",
                "PDF appears corrupted or unreadable.",
            )
        return None

    @staticmethod
    def _check_image(content: bytes, filename: str) -> FileValidationIssue | None:
        try:
            from io import BytesIO

            from PIL import Image

            with Image.open(BytesIO(content)) as img:
                img.verify()
        except Exception as exc:
            logger.warning("Image validation failed for %s: %s", filename, exc)
            return FileValidationIssue(
                filename,
                "unreadable_image",
                "Image appears corrupted or unreadable.",
            )
        return None
