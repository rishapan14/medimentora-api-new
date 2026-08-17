"""Phase 20 — educational safety wording for X-ray AI.

Never claim definitive diagnoses. Prefer:
  "The AI detected findings that may be consistent with …"

Always surface the short educational disclaimer.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.xray_analysis_model import XRAY_SHORT_DISCLAIMER

__all__ = [
  "XRAY_SHORT_DISCLAIMER",
  "hedge_finding_label",
  "sanitize_educational_text",
  "ensure_short_disclaimer",
  "safety_payload",
]

_FORBIDDEN_PATTERNS = (
  re.compile(r"\byou have\b", re.I),
  re.compile(r"\byou are diagnosed\b", re.I),
  re.compile(r"\bdiagnosed with\b", re.I),
  re.compile(r"\bthis (is|confirms)\b.{0,40}\b(pneumonia|fracture|cancer|effusion|atelectasis)\b", re.I),
  re.compile(r"\bdefinitive diagnosis\b", re.I),
  re.compile(r"\bprescribe[sd]?\b", re.I),
  re.compile(r"\btake\s+\d+\s*mg\b", re.I),
  re.compile(r"\bstart\s+(antibiotics|steroids|chemotherapy)\b", re.I),
)

_YOU_HAVE_RE = re.compile(
  r"\byou have\s+(?:a\s+|an\s+)?([a-zA-Z][\w\s\-]{1,60}?)\b",
  re.I,
)
_DIAGNOSED_RE = re.compile(
  r"\b(?:you are )?diagnosed with\s+([a-zA-Z][\w\s\-]{1,60}?)\b",
  re.I,
)
_POSSIBLE_PREFIX_RE = re.compile(r"^\s*possible\s+", re.I)


def hedge_finding_label(label: str | None) -> str:
  """Display-safe finding phrase (Phase 20).

  ``Possible Pneumonia`` →
  ``The AI detected findings that may be consistent with pneumonia.``
  """
  raw = (label or "").strip()
  if not raw:
    return "The AI detected educational observations that require clinical interpretation."

  lowered = raw.lower()
  if "may be consistent with" in lowered or "possible findings that may" in lowered:
    return raw if raw.endswith(".") else f"{raw}."

  condition = _POSSIBLE_PREFIX_RE.sub("", raw).strip(" .")
  if not condition:
    condition = "an unspecified finding"
  # Prefer lowercase clinical noun phrase after the hedge stem.
  condition_fmt = condition[0].lower() + condition[1:] if len(condition) > 1 else condition.lower()
  return f"The AI detected findings that may be consistent with {condition_fmt}."


def sanitize_educational_text(text: str | None) -> str:
  """Rewrite definitive diagnosis claims into educational hedging."""
  if not text:
    return ""
  out = str(text)

  def _you_have(match: re.Match[str]) -> str:
    condition = (match.group(1) or "").strip(" .,;")
    return f"findings that may be consistent with {condition}"

  def _diagnosed(match: re.Match[str]) -> str:
    condition = (match.group(1) or "").strip(" .,;")
    return f"findings that may be consistent with {condition}"

  out = _YOU_HAVE_RE.sub(_you_have, out)
  out = _DIAGNOSED_RE.sub(_diagnosed, out)

  # Soften remaining forbidden stems without inventing content.
  for pattern in _FORBIDDEN_PATTERNS:
    if pattern.search(out):
      out = pattern.sub("may be consistent with findings suggesting", out)
  return out


def ensure_short_disclaimer(text: str | None = None) -> str:
  """Return text that always includes the Phase 20 short disclaimer."""
  base = (text or "").strip()
  if XRAY_SHORT_DISCLAIMER.lower() in base.lower():
    return base
  if not base:
    return XRAY_SHORT_DISCLAIMER
  return f"{XRAY_SHORT_DISCLAIMER}\n\n{base}"


def safety_payload() -> dict[str, Any]:
  """Common safety flags for API/export payloads."""
  return {
    "educational_only": True,
    "not_a_diagnosis": True,
    "short_disclaimer": XRAY_SHORT_DISCLAIMER,
    "never_definitive_diagnosis": True,
  }
