"""Read and validate DICOM pixel data for educational X-ray uploads.

Converts a single-frame radiographic DICOM into an 8-bit PNG suitable for the
existing OpenCV/PIL preprocessing pipeline. Multi-frame / non-image DICOMs
are rejected with clear errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

logger = logging.getLogger(__name__)


class DicomReadError(Exception):
  """Raised when a DICOM file cannot be validated or decoded."""

  def __init__(self, code: str, message: str):
    super().__init__(message)
    self.code = code
    self.message = message


@dataclass(frozen=True)
class DicomReadResult:
  """Decoded DICOM radiograph ready for storage."""

  width: int
  height: int
  png_bytes: bytes
  modality: str | None = None
  bits_stored: int | None = None


def read_dicom_pixels(raw: bytes) -> DicomReadResult:
  """Validate DICOM bytes and return PNG pixels + dimensions.

  Raises:
    DicomReadError: when the file is missing, corrupt, or not a usable image.
  """
  if not raw:
    raise DicomReadError("empty_file", "DICOM file is empty.")

  try:
    import numpy as np
    import pydicom
    from pydicom.errors import InvalidDicomError
  except ImportError as exc:  # pragma: no cover
    raise DicomReadError(
      "dicom_dependency_missing",
      "DICOM support requires the pydicom package. Ask your administrator to install it.",
    ) from exc

  try:
    ds = pydicom.dcmread(BytesIO(raw), force=False)
  except InvalidDicomError as exc:
    raise DicomReadError(
      "corrupted_dicom",
      "File is not a valid DICOM radiograph or appears corrupted.",
    ) from exc
  except Exception as exc:
    logger.warning("DICOM parse failed: %s", exc)
    raise DicomReadError(
      "corrupted_dicom",
      "Unable to read DICOM file. The file may be corrupted or incomplete.",
    ) from exc

  if not hasattr(ds, "PixelData") and not hasattr(ds, "FloatPixelData"):
    raise DicomReadError(
      "dicom_no_pixels",
      "DICOM file contains no pixel data. Upload a radiographic image DICOM.",
    )

  try:
    arr = ds.pixel_array
  except Exception as exc:
    logger.warning("DICOM pixel decode failed: %s", exc)
    raise DicomReadError(
      "corrupted_dicom",
      "DICOM pixel data could not be decoded. The file may use an unsupported transfer syntax.",
    ) from exc

  arr = np.asarray(arr)
  if arr.ndim == 3:
    # Multi-frame or RGB — take first frame / convert
    if arr.shape[0] < 2 and arr.shape[-1] in (3, 4):
      # HWC color
      arr = arr[..., 0] if arr.shape[-1] >= 1 else arr[:, :, 0]
    elif arr.shape[0] >= 1 and arr.ndim == 3:
      arr = arr[0]
    else:
      raise DicomReadError(
        "dicom_unsupported",
        "Multi-dimensional DICOM images are not supported. Upload a single-frame radiograph.",
      )
  if arr.ndim != 2:
    raise DicomReadError(
      "dicom_unsupported",
      "Only single-frame grayscale radiographic DICOMs are supported.",
    )

  height, width = int(arr.shape[0]), int(arr.shape[1])
  if width < 1 or height < 1:
    raise DicomReadError("unreadable_image", "DICOM image has invalid dimensions.")

  # Window to 8-bit for PNG storage (educational pipeline)
  flat = arr.astype(np.float64)
  lo = float(np.min(flat))
  hi = float(np.max(flat))
  if hi <= lo:
    scaled = np.zeros_like(flat, dtype=np.uint8)
  else:
    scaled = ((flat - lo) / (hi - lo) * 255.0).clip(0, 255).astype(np.uint8)

  try:
    from PIL import Image

    img = Image.fromarray(scaled, mode="L")
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
  except Exception as exc:
    raise DicomReadError(
      "dicom_convert_failed",
      "DICOM was readable but could not be converted for analysis.",
    ) from exc

  modality = str(getattr(ds, "Modality", "") or "") or None
  bits = getattr(ds, "BitsStored", None)
  try:
    bits_stored = int(bits) if bits is not None else None
  except (TypeError, ValueError):
    bits_stored = None

  return DicomReadResult(
    width=width,
    height=height,
    png_bytes=png_bytes,
    modality=modality,
    bits_stored=bits_stored,
  )
