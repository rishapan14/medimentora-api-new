"""Phase 1 — X-ray upload validation tests (JPG/PNG/DICOM)."""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from werkzeug.datastructures import FileStorage

from app.services.xray.validators import XrayUploadValidator
from tests.conftest import make_filestorage, make_png_bytes


def _make_jpeg_bytes(width: int = 128, height: int = 128) -> bytes:
  from PIL import Image

  img = Image.new("L", (width, height), color=90)
  buf = BytesIO()
  img.save(buf, format="JPEG", quality=85)
  return buf.getvalue()


def _make_minimal_dicom_bytes(width: int = 128, height: int = 128) -> bytes:
  """Build a valid single-frame radiographic DICOM in memory."""
  pydicom = pytest.importorskip("pydicom")
  from pydicom.dataset import Dataset, FileMetaDataset
  from pydicom.uid import ExplicitVRLittleEndian, generate_uid

  pixel = np.arange(width * height, dtype=np.uint16).reshape((height, width)) % 4096

  file_meta = FileMetaDataset()
  file_meta.MediaStorageSOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
  file_meta.MediaStorageSOPInstanceUID = generate_uid()
  file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
  file_meta.ImplementationClassUID = generate_uid()

  ds = Dataset()
  ds.file_meta = file_meta
  ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
  ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
  ds.Modality = "DX"
  ds.SamplesPerPixel = 1
  ds.PhotometricInterpretation = "MONOCHROME2"
  ds.Rows = height
  ds.Columns = width
  ds.BitsAllocated = 16
  ds.BitsStored = 12
  ds.HighBit = 11
  ds.PixelRepresentation = 0
  ds.PixelData = pixel.tobytes()

  buf = BytesIO()
  ds.save_as(buf, enforce_file_format=True)
  return buf.getvalue()


def test_validate_accepts_png():
  validator = XrayUploadValidator(min_width=64, min_height=64)
  result = validator.validate([make_filestorage("ok.png")])
  assert result.ok
  assert len(result.files) == 1
  assert result.files[0].file_type in ("png", "jpg", "jpeg")
  assert result.files[0].width >= 64
  assert result.files[0].content_hash


def test_validate_accepts_jpeg():
  raw = _make_jpeg_bytes()
  fs = FileStorage(stream=BytesIO(raw), filename="chest.jpg", content_type="image/jpeg")
  result = XrayUploadValidator(min_width=64, min_height=64).validate([fs])
  assert result.ok
  assert result.files[0].file_type == "jpg"


def test_validate_rejects_unsupported_extension():
  validator = XrayUploadValidator()
  bad = FileStorage(stream=BytesIO(b"not-an-image"), filename="note.txt", content_type="text/plain")
  result = validator.validate([bad])
  assert not result.ok
  assert result.errors
  assert any(
    e.code in ("unsupported_type", "unsupported_extension", "invalid_type")
    or "txt" in e.message.lower()
    or "unsupported" in e.message.lower()
    for e in result.errors
  )


def test_validate_rejects_fake_dicom():
  validator = XrayUploadValidator()
  dcm = FileStorage(
    stream=BytesIO(b"DICM" + b"\x00" * 20),
    filename="scan.dcm",
    content_type="application/dicom",
  )
  result = validator.validate([dcm])
  assert not result.ok
  assert any(
    e.code in ("corrupted_dicom", "dicom_no_pixels", "corrupted_image")
    or "dicom" in e.message.lower()
    for e in result.errors
  )


def test_validate_accepts_valid_dicom():
  raw = _make_minimal_dicom_bytes(128, 128)
  fs = FileStorage(stream=BytesIO(raw), filename="study.dcm", content_type="application/dicom")
  result = XrayUploadValidator(min_width=64, min_height=64).validate([fs])
  assert result.ok, [e.message for e in result.errors]
  assert len(result.files) == 1
  item = result.files[0]
  assert item.file_type == "dcm"
  assert item.width == 128
  assert item.height == 128
  assert item.normalized_bytes is not None
  assert item.normalized_bytes[:8] == b"\x89PNG\r\n\x1a\n"
  assert item.stored_extension == "png"


def test_validate_rejects_tiny_resolution():
  validator = XrayUploadValidator(min_width=64, min_height=64)
  tiny = make_filestorage("tiny.png", width=32, height=32)
  result = validator.validate([tiny])
  assert not result.ok
  assert any(
    "resolution" in e.message.lower() or "small" in e.message.lower() or "dimension" in e.message.lower()
    for e in result.errors
  )


def test_validate_rejects_corrupt_image():
  validator = XrayUploadValidator()
  corrupt = FileStorage(
    stream=BytesIO(b"this-is-not-a-png"),
    filename="corrupt.png",
    content_type="image/png",
  )
  result = validator.validate([corrupt])
  assert not result.ok
  assert any(e.code == "corrupted_image" for e in result.errors)


def test_validate_rejects_format_mismatch_png_named_jpg():
  raw = make_png_bytes(128, 128)
  fs = FileStorage(stream=BytesIO(raw), filename="lied.jpg", content_type="image/jpeg")
  result = XrayUploadValidator(min_width=64, min_height=64).validate([fs])
  assert not result.ok
  assert any(e.code == "format_mismatch" for e in result.errors)


def test_validate_rejects_invalid_mime():
  raw = make_png_bytes(128, 128)
  fs = FileStorage(stream=BytesIO(raw), filename="ok.png", content_type="text/plain")
  result = XrayUploadValidator(min_width=64, min_height=64).validate([fs])
  assert not result.ok
  assert any(e.code == "invalid_mime" for e in result.errors)


def test_validate_detects_duplicate_hash():
  raw = make_png_bytes()
  h = __import__("hashlib").sha256(raw).hexdigest()
  validator = XrayUploadValidator(existing_hashes={h})
  fs = FileStorage(stream=BytesIO(raw), filename="dup.png", content_type="image/png")
  result = validator.validate([fs])
  assert not result.ok
  assert any("duplicate" in e.message.lower() or "duplicate" in e.code.lower() for e in result.errors)


def test_sniff_detects_jpeg_png_dicom():
  from app.services.xray.preprocessing.format_sniff import DetectedImageFormat, sniff_image_format

  assert sniff_image_format(_make_jpeg_bytes()).format == DetectedImageFormat.JPEG
  assert sniff_image_format(make_png_bytes(64, 64)).format == DetectedImageFormat.PNG
  assert sniff_image_format(_make_minimal_dicom_bytes()).format == DetectedImageFormat.DICOM
  assert sniff_image_format(b"hello").format == DetectedImageFormat.UNKNOWN
