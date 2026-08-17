"""Healthy educational reference library package (Phase 9).

Disk layout (orientation is an optional 5th segment used by admin uploads):

  reference_library/
    {body_part}/{projection}/{age_group}/{gender}/[{orientation}/]{file}

Required metadata: body_part, projection, age_group, gender, license, source.

Public API stays import-compatible:

  from app.services.xray.reference_library import ReferenceLibraryService
"""

from app.services.xray.reference_xray_library_service import EMPTY_LIBRARY_MESSAGE as _CANONICAL_EMPTY

from app.services.xray.reference_library.service import (
  ADULT_AGE_MAX,
  CATALOG_FILENAME,
  CATALOG_VERSION,
  CHILD_AGE_MAX,
  CHILD_BAND_MAX,
  IMAGE_EXTENSIONS,
  INFANT_AGE_MAX,
  PLACEHOLDER_MARKERS,
  TEEN_AGE_MAX,
  ReferenceImage,
  ReferenceLibraryService,
  ReferenceSelectionResult,
)
from app.services.xray.reference_library.selector import (
  ReferenceLibrarySelector,
  select_best_healthy_reference,
)

# Single canonical empty-library message (Phase 9)
EMPTY_LIBRARY_MESSAGE = _CANONICAL_EMPTY

__all__ = [
  "EMPTY_LIBRARY_MESSAGE",
  "ADULT_AGE_MAX",
  "CATALOG_FILENAME",
  "CATALOG_VERSION",
  "CHILD_AGE_MAX",
  "CHILD_BAND_MAX",
  "IMAGE_EXTENSIONS",
  "INFANT_AGE_MAX",
  "PLACEHOLDER_MARKERS",
  "TEEN_AGE_MAX",
  "ReferenceImage",
  "ReferenceLibraryService",
  "ReferenceSelectionResult",
  "ReferenceLibrarySelector",
  "select_best_healthy_reference",
]
