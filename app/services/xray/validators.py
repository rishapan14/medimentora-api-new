"""X-ray image upload validation (Phase 1 — Image Validation).

Supports JPG, JPEG, PNG, and DICOM (.dcm / .dicom).

Rejects non-images, corrupted files, extremely small images, wrong formats,
content/extension mismatches, and invalid DICOM payloads.

DICOM files are validated and converted to PNG bytes for the existing
OpenCV/PIL analysis pipeline while preserving file_type=dcm metadata.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from io import BytesIO
from typing import Iterable

from werkzeug.datastructures import FileStorage

from app.services.xray.dicom import DicomReadError, read_dicom_pixels
from app.services.xray.preprocessing.format_sniff import DetectedImageFormat, sniff_image_format

logger = logging.getLogger(__name__)

ALLOWED_RASTER_EXTENSIONS = frozenset({"jpg", "jpeg", "png"})
ALLOWED_DICOM_EXTENSIONS = frozenset({"dcm", "dicom"})
ALLOWED_EXTENSIONS = ALLOWED_RASTER_EXTENSIONS | ALLOWED_DICOM_EXTENSIONS

ALLOWED_MIME_TYPES = frozenset(
  {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "application/dicom",
    "application/dicom+json",
    "application/octet-stream",
  }
)

# Extensions that claim to be images but are never accepted as X-rays here
_REJECT_HINTS = {
  "gif": "GIF animations are not supported for X-ray analysis.",
  "bmp": "BMP is not supported. Please upload JPG, JPEG, PNG, or DICOM.",
  "webp": "WebP is not supported for patient X-ray uploads. Use JPG, JPEG, PNG, or DICOM.",
  "tif": "TIFF is not supported for patient X-ray uploads. Use JPG, JPEG, PNG, or DICOM.",
  "tiff": "TIFF is not supported for patient X-ray uploads. Use JPG, JPEG, PNG, or DICOM.",
  "pdf": "PDF is not an X-ray image format. Upload JPG, JPEG, PNG, or DICOM.",
  "svg": "SVG is not supported. Upload a radiographic JPG, JPEG, PNG, or DICOM.",
}


@dataclass
class XrayValidationIssue:
  """One validation problem for a single X-ray file."""

  filename: str
  code: str
  message: str


@dataclass
class ValidatedXrayUpload:
  """An X-ray image that passed validation and is ready to save."""

  storage: FileStorage
  filename: str
  extension: str
  file_type: str  # jpg | jpeg | png | dcm
  size_bytes: int
  content_hash: str
  width: int
  height: int
  mime_type: str | None = None
  # When set (DICOM), upload service writes these PNG bytes instead of raw stream
  normalized_bytes: bytes | None = None
  stored_extension: str | None = None  # e.g. "png" after DICOM conversion


@dataclass
class XrayValidationResult:
  """Outcome of validating a multi-file X-ray upload."""

  ok: bool
  files: list[ValidatedXrayUpload] = field(default_factory=list)
  errors: list[XrayValidationIssue] = field(default_factory=list)
  total_size_bytes: int = 0

  def error_messages(self) -> list[str]:
    return [f"{e.filename}: {e.message}" for e in self.errors]


class XrayUploadValidator:
  """Validate one or more X-ray image uploads (Phase 1)."""

  def __init__(
    self,
    max_files: int = 20,
    max_total_bytes: int = 100 * 1024 * 1024,
    max_file_bytes: int | None = None,
    min_width: int = 64,
    min_height: int = 64,
    max_width: int = 10000,
    max_height: int = 10000,
    existing_hashes: Iterable[str] | None = None,
    allowed_extensions: Iterable[str] | None = None,
  ):
    self.max_files = max_files
    self.max_total_bytes = max_total_bytes
    self.max_file_bytes = max_file_bytes or max_total_bytes
    self.min_width = min_width
    self.min_height = min_height
    self.max_width = max_width
    self.max_height = max_height
    self.existing_hashes = set(existing_hashes or [])
    if allowed_extensions is not None:
      self.allowed_extensions = frozenset(e.lower().lstrip(".") for e in allowed_extensions)
    else:
      self.allowed_extensions = ALLOWED_EXTENSIONS

  def validate(self, files: Iterable[FileStorage | None]) -> XrayValidationResult:
    """Validate a list of Werkzeug FileStorage objects."""
    result = XrayValidationResult(ok=True)
    seen_hashes: set[str] = set()
    seen_names: set[str] = set()

    raw_files = [f for f in files if f is not None and getattr(f, "filename", None)]
    if not raw_files:
      result.ok = False
      result.errors.append(
        XrayValidationIssue(
          filename="(none)",
          code="no_files",
          message="At least one X-ray image (JPG, JPEG, PNG, or DICOM) is required.",
        )
      )
      return result

    if len(raw_files) > self.max_files:
      result.ok = False
      result.errors.append(
        XrayValidationIssue(
          filename="(batch)",
          code="too_many_files",
          message=(
            f"Maximum {self.max_files} X-ray images allowed per upload "
            f"(received {len(raw_files)})."
          ),
        )
      )
      return result

    for storage in raw_files:
      item = self._validate_one(storage, seen_hashes, seen_names)
      if isinstance(item, XrayValidationIssue):
        result.errors.append(item)
        continue
      result.files.append(item)
      result.total_size_bytes += item.size_bytes

    if result.total_size_bytes > self.max_total_bytes:
      result.ok = False
      mb = self.max_total_bytes / (1024 * 1024)
      result.errors.append(
        XrayValidationIssue(
          filename="(batch)",
          code="total_too_large",
          message=f"Total upload size exceeds {mb:.0f} MB.",
        )
      )

    if result.errors:
      result.ok = False
      result.files = []
    return result

  def _validate_one(
    self,
    storage: FileStorage,
    seen_hashes: set[str],
    seen_names: set[str],
  ) -> ValidatedXrayUpload | XrayValidationIssue:
    filename = (storage.filename or "").strip()
    if not filename:
      return XrayValidationIssue("", "missing_filename", "Filename is missing.")

    name_key = filename.lower()
    if name_key in seen_names:
      return XrayValidationIssue(filename, "duplicate_name", "Duplicate filename in this upload.")
    seen_names.add(name_key)

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not extension:
      return XrayValidationIssue(
        filename,
        "unsupported_type",
        "File has no extension. Allowed: JPG, JPEG, PNG, DICOM (.dcm).",
      )

    if extension in _REJECT_HINTS:
      return XrayValidationIssue(filename, "unsupported_type", _REJECT_HINTS[extension])

    if extension not in self.allowed_extensions:
      return XrayValidationIssue(
        filename,
        "unsupported_type",
        f"Unsupported format '.{extension}'. Allowed: JPG, JPEG, PNG, DICOM (.dcm).",
      )

    mime = (storage.mimetype or "").lower() or None
    if mime and mime not in ALLOWED_MIME_TYPES and not mime.startswith("image/"):
      return XrayValidationIssue(
        filename,
        "invalid_mime",
        f"Invalid content type '{mime}'. Upload a radiographic JPG, JPEG, PNG, or DICOM file.",
      )
    if mime and mime.startswith("image/") and mime not in ALLOWED_MIME_TYPES:
      # e.g. image/gif, image/webp declared by browser
      if extension in ALLOWED_RASTER_EXTENSIONS:
        return XrayValidationIssue(
          filename,
          "invalid_mime",
          f"MIME type '{mime}' is not accepted for X-ray uploads. Use JPG, JPEG, or PNG.",
        )

    raw = storage.stream.read()
    try:
      storage.stream.seek(0)
    except Exception:
      pass
    size = len(raw)
    if size == 0:
      return XrayValidationIssue(filename, "empty_file", "File is empty.")
    if size > self.max_file_bytes:
      mb = self.max_file_bytes / (1024 * 1024)
      return XrayValidationIssue(
        filename,
        "file_too_large",
        f"File exceeds maximum size of {mb:.0f} MB.",
      )

    content_hash = hashlib.sha256(raw).hexdigest()
    if content_hash in seen_hashes:
      return XrayValidationIssue(filename, "duplicate_content", "Duplicate image content in this upload.")
    if content_hash in self.existing_hashes:
      return XrayValidationIssue(
        filename,
        "duplicate_existing",
        "This X-ray was already uploaded to your history.",
      )
    seen_hashes.add(content_hash)

    sniffed = sniff_image_format(raw)
    is_dicom_ext = extension in ALLOWED_DICOM_EXTENSIONS

    if is_dicom_ext or sniffed.format == DetectedImageFormat.DICOM:
      return self._validate_dicom(
        storage=storage,
        filename=filename,
        extension=extension if is_dicom_ext else "dcm",
        raw=raw,
        size=size,
        content_hash=content_hash,
        mime=mime,
        sniffed=sniffed,
      )

    return self._validate_raster(
      storage=storage,
      filename=filename,
      extension=extension,
      raw=raw,
      size=size,
      content_hash=content_hash,
      mime=mime,
      sniffed=sniffed,
    )

  def _validate_raster(
    self,
    *,
    storage: FileStorage,
    filename: str,
    extension: str,
    raw: bytes,
    size: int,
    content_hash: str,
    mime: str | None,
    sniffed,
  ) -> ValidatedXrayUpload | XrayValidationIssue:
    if sniffed.format == DetectedImageFormat.UNKNOWN:
      return XrayValidationIssue(
        filename,
        "corrupted_image",
        "File is not a valid JPG or PNG image (unrecognized format or corrupted).",
      )

    expected = {
      DetectedImageFormat.JPEG: {"jpg", "jpeg"},
      DetectedImageFormat.PNG: {"png"},
    }.get(sniffed.format, set())
    if expected and extension not in expected:
      return XrayValidationIssue(
        filename,
        "format_mismatch",
        (
          f"File extension '.{extension}' does not match the actual "
          f"{sniffed.format.value.upper()} image content. "
          "Rename the file or re-export in the correct format."
        ),
      )

    dims = self._check_pil_image(raw, filename)
    if isinstance(dims, XrayValidationIssue):
      return dims
    width, height = dims

    dim_issue = self._check_dimensions(filename, width, height)
    if dim_issue:
      return dim_issue

    return ValidatedXrayUpload(
      storage=storage,
      filename=filename,
      extension=extension,
      file_type=extension,
      size_bytes=size,
      content_hash=content_hash,
      width=width,
      height=height,
      mime_type=mime,
    )

  def _validate_dicom(
    self,
    *,
    storage: FileStorage,
    filename: str,
    extension: str,
    raw: bytes,
    size: int,
    content_hash: str,
    mime: str | None,
    sniffed,
  ) -> ValidatedXrayUpload | XrayValidationIssue:
    if sniffed.format not in (DetectedImageFormat.DICOM, DetectedImageFormat.UNKNOWN):
      # Extension says DICOM but bytes are a plain JPEG/PNG
      return XrayValidationIssue(
        filename,
        "format_mismatch",
        (
          f"File extension '.{extension}' claims DICOM, but the content is a "
          f"{sniffed.format.value.upper()} image. Upload a real .dcm file or rename correctly."
        ),
      )

    try:
      decoded = read_dicom_pixels(raw)
    except DicomReadError as exc:
      return XrayValidationIssue(filename, exc.code, exc.message)

    dim_issue = self._check_dimensions(filename, decoded.width, decoded.height)
    if dim_issue:
      return dim_issue

    return ValidatedXrayUpload(
      storage=storage,
      filename=filename,
      extension=extension if extension in ALLOWED_DICOM_EXTENSIONS else "dcm",
      file_type="dcm",
      size_bytes=size,
      content_hash=content_hash,
      width=decoded.width,
      height=decoded.height,
      mime_type=mime or "application/dicom",
      normalized_bytes=decoded.png_bytes,
      stored_extension="png",
    )

  def _check_dimensions(self, filename: str, width: int, height: int) -> XrayValidationIssue | None:
    if width < self.min_width or height < self.min_height:
      return XrayValidationIssue(
        filename,
        "resolution_too_low",
        (
          f"Image resolution is too low ({width}x{height}). "
          f"Minimum required is {self.min_width}x{self.min_height} pixels."
        ),
      )
    if width > self.max_width or height > self.max_height:
      return XrayValidationIssue(
        filename,
        "resolution_too_high",
        (
          f"Image resolution is too large ({width}x{height}). "
          f"Maximum allowed is {self.max_width}x{self.max_height} pixels."
        ),
      )
    return None

  @staticmethod
  def _check_pil_image(raw: bytes, filename: str) -> tuple[int, int] | XrayValidationIssue:
    """Reject corrupted / unreadable raster images; return (width, height)."""
    try:
      from PIL import Image

      with Image.open(BytesIO(raw)) as img:
        img.verify()
      with Image.open(BytesIO(raw)) as img:
        width, height = img.size
        img.load()
      if width < 1 or height < 1:
        return XrayValidationIssue(filename, "unreadable_image", "Image has invalid dimensions.")
      return width, height
    except Exception as exc:
      logger.warning("X-ray image validation failed for %s: %s", filename, exc)
      return XrayValidationIssue(
        filename,
        "corrupted_image",
        "Image appears corrupted or unreadable. Please upload a clear X-ray JPG, JPEG, or PNG.",
      )
