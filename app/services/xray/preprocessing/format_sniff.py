"""Magic-byte image format detection for Phase 1 upload validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.xray.dicom.detect import looks_like_dicom


class DetectedImageFormat(str, Enum):
  JPEG = "jpeg"
  PNG = "png"
  DICOM = "dicom"
  UNKNOWN = "unknown"


@dataclass(frozen=True)
class SniffResult:
  format: DetectedImageFormat
  matched_extension: str | None  # canonical extension without dot


_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def sniff_image_format(raw: bytes) -> SniffResult:
  """Detect image/DICOM format from file content (not the filename)."""
  if not raw:
    return SniffResult(DetectedImageFormat.UNKNOWN, None)
  if raw.startswith(_JPEG_MAGIC):
    return SniffResult(DetectedImageFormat.JPEG, "jpg")
  if raw.startswith(_PNG_MAGIC):
    return SniffResult(DetectedImageFormat.PNG, "png")
  if looks_like_dicom(raw):
    return SniffResult(DetectedImageFormat.DICOM, "dcm")
  return SniffResult(DetectedImageFormat.UNKNOWN, None)
