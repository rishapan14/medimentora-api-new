"""Lightweight DICOM detection via magic bytes (no pixel decode)."""

from __future__ import annotations

# Part 10 meta header: "DICM" at byte offset 128
_DICOM_MAGIC_OFFSET = 128
_DICOM_MAGIC = b"DICM"


def looks_like_dicom(raw: bytes) -> bool:
  """Return True when bytes match DICOM Part 10 preamble or common prefixes."""
  if not raw:
    return False
  if len(raw) >= _DICOM_MAGIC_OFFSET + 4:
    if raw[_DICOM_MAGIC_OFFSET : _DICOM_MAGIC_OFFSET + 4] == _DICOM_MAGIC:
      return True
  # Some exporters omit the 128-byte preamble and start at the file meta group
  if raw.startswith(b"\x00\x00\x01\x00") or raw.startswith(b"\x00\x00\x00\x01"):
    return True
  # Explicit VR little-endian transfer syntax marker often near start after preamble
  if b"DICM" in raw[:256]:
    return True
  return False
