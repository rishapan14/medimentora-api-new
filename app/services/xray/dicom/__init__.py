"""DICOM support for educational X-ray uploads (Phase 1+).

Validation and pixel extraction only — never used for diagnosis claims.
"""

from app.services.xray.dicom.detect import looks_like_dicom
from app.services.xray.dicom.reader import DicomReadError, DicomReadResult, read_dicom_pixels

__all__ = [
  "looks_like_dicom",
  "DicomReadError",
  "DicomReadResult",
  "read_dicom_pixels",
]
