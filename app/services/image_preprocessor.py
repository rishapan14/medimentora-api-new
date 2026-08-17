"""Production image enhancement pipeline for medical document OCR.

Pipeline (all steps fail-safe — any failure falls back to the previous stage):

    load (EXIF auto-rotate) -> resize -> shadow removal -> denoise
    -> contrast (CLAHE) -> deskew -> sharpen -> [optional] adaptive threshold

Design notes:
- Output is an enhanced GRAYSCALE image by default (not hard-binarized).
  PaddleOCR/RapidOCR detection models perform better on grayscale with good
  contrast than on binary images, and grayscale preserves table ruling lines
  and faint print that hard thresholding destroys.
- Adaptive thresholding is available behind `IMAGE_ENHANCE_BINARIZE` for
  engines that benefit from it (e.g. Tesseract on clean scans).
- Deskew is limited to small angles (±15°); page-level 90/180/270 rotation is
  left to the OCR engine's angle classifier, which is more reliable.
- Geometry-changing steps use border replication and cubic interpolation so
  multi-column layouts and tables survive intact.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Skew angles below this are noise; above the max is likely a rotated page,
# which the OCR engine's orientation classifier handles better than we can.
MIN_SKEW_DEGREES = 0.3
MAX_SKEW_DEGREES = 15.0

# OCR accuracy drops sharply below ~1000px on the short side for lab reports.
TARGET_MIN_DIMENSION = 1200
MAX_DIMENSION = 4200


@dataclass
class PreprocessResult:
    """Outcome of the enhancement pipeline."""

    path: str
    success: bool = True
    applied_steps: list[str] = field(default_factory=list)
    skew_angle: float = 0.0
    original_size: tuple[int, int] = (0, 0)
    final_size: tuple[int, int] = (0, 0)
    processing_time_ms: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "success": self.success,
            "applied_steps": self.applied_steps,
            "skew_angle": round(self.skew_angle, 2),
            "original_size": list(self.original_size),
            "final_size": list(self.final_size),
            "processing_time_ms": self.processing_time_ms,
            "warnings": self.warnings,
        }


class ImagePreprocessor:
    """OpenCV document enhancement for OCR.

    Usage:
        result = ImagePreprocessor().enhance("scan.jpg")
        ocr_input_path = result.path
    """

    def __init__(
        self,
        binarize: bool = False,
        target_min_dim: int = TARGET_MIN_DIMENSION,
        max_dim: int = MAX_DIMENSION,
    ):
        self.binarize = binarize
        self.target_min_dim = target_min_dim
        self.max_dim = max_dim

    # ------------------------------------------------------------------ API

    def enhance(self, image_path: str) -> PreprocessResult:
        """Run the full enhancement pipeline. Never raises; on any failure the
        original file path is returned so OCR can still proceed."""
        started = time.perf_counter()
        result = PreprocessResult(path=image_path)

        if not os.path.isfile(image_path):
            result.success = False
            result.warnings.append("Input file not found; skipping enhancement.")
            return result

        try:
            import cv2
        except ImportError:
            result.success = False
            result.warnings.append("OpenCV not installed; using original image.")
            return result

        image = self._load_auto_rotated(image_path)
        if image is None:
            result.success = False
            result.warnings.append("Could not decode image; using original file.")
            return result

        result.original_size = (image.shape[1], image.shape[0])
        result.applied_steps.append("exif_auto_rotate")

        image = self._apply(result, "resize", self._resize, image)
        gray = self._apply(result, "grayscale", self._to_grayscale, image)
        gray = self._apply(result, "shadow_removal", self._remove_shadows, gray)
        gray = self._apply(result, "denoise", self._denoise, gray)
        gray = self._apply(result, "contrast_clahe", self._enhance_contrast, gray)
        gray, angle = self._deskew_step(result, gray)
        result.skew_angle = angle
        gray = self._apply(result, "sharpen", self._sharpen, gray)

        if self.binarize:
            gray = self._apply(result, "adaptive_threshold", self._adaptive_threshold, gray)

        result.final_size = (gray.shape[1], gray.shape[0])

        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            cv2.imwrite(tmp.name, gray)
            result.path = tmp.name
        except Exception:
            logger.exception("Failed to save enhanced image; using original.")
            result.path = image_path
            result.warnings.append("Could not save enhanced image; original used.")

        result.processing_time_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Image enhancement done in %dms — steps=%s skew=%.2f° size=%s->%s",
            result.processing_time_ms,
            ",".join(result.applied_steps),
            result.skew_angle,
            result.original_size,
            result.final_size,
        )
        return result

    # -------------------------------------------------------- pipeline steps

    def _apply(self, result: PreprocessResult, step: str, fn, image):
        """Run one step; on failure keep the previous image and record a warning."""
        try:
            out = fn(image)
            result.applied_steps.append(step)
            return out
        except Exception:
            logger.exception("Enhancement step failed: %s", step)
            result.warnings.append(f"Step '{step}' failed and was skipped.")
            return image

    @staticmethod
    def _load_auto_rotated(image_path: str):
        """Load respecting EXIF orientation (phone photos of reports)."""
        import cv2
        import numpy as np

        try:
            from PIL import Image, ImageOps

            with Image.open(image_path) as pil_img:
                pil_img = ImageOps.exif_transpose(pil_img)
                rgb = pil_img.convert("RGB")
                return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
        except Exception:
            return cv2.imread(image_path, cv2.IMREAD_COLOR)

    def _resize(self, image):
        """Upscale small images / downscale huge ones for stable OCR."""
        import cv2

        h, w = image.shape[:2]
        min_dim, max_dim = min(h, w), max(h, w)

        if min_dim < self.target_min_dim:
            scale = self.target_min_dim / min_dim
            # Cap so the long side never explodes past max_dim
            scale = min(scale, self.max_dim / max_dim)
            if scale > 1.01:
                return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        elif max_dim > self.max_dim:
            scale = self.max_dim / max_dim
            return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return image

    @staticmethod
    def _to_grayscale(image):
        import cv2

        if image.ndim == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    @staticmethod
    def _remove_shadows(gray):
        """Normalize uneven illumination (shadows from phone photos).

        Estimates the background with a large median blur of a dilated image,
        then divides it out. Text and table lines are preserved because they
        are much smaller than the blur kernel.
        """
        import cv2
        import numpy as np

        kernel = np.ones((7, 7), np.uint8)
        background = cv2.medianBlur(cv2.dilate(gray, kernel), 31)
        # Avoid division by zero in fully black regions
        background = np.clip(background, 1, 255)
        normalized = cv2.divide(gray, background, scale=255)
        return normalized

    @staticmethod
    def _denoise(gray):
        import cv2

        # h=7 removes scanner grain without eating thin table rules
        return cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)

    @staticmethod
    def _enhance_contrast(gray):
        """CLAHE: local contrast boost that doesn't blow out already-dark text."""
        import cv2

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _deskew_step(self, result: PreprocessResult, gray):
        """Detect and correct small skew angles."""
        try:
            angle = self._estimate_skew(gray)
        except Exception:
            logger.exception("Skew estimation failed.")
            result.warnings.append("Skew estimation failed; deskew skipped.")
            return gray, 0.0

        if abs(angle) < MIN_SKEW_DEGREES or abs(angle) > MAX_SKEW_DEGREES:
            return gray, 0.0

        try:
            rotated = self._rotate(gray, angle)
            result.applied_steps.append("deskew")
            return rotated, angle
        except Exception:
            logger.exception("Deskew rotation failed.")
            result.warnings.append("Deskew rotation failed; original orientation kept.")
            return gray, 0.0

    @staticmethod
    def _estimate_skew(gray) -> float:
        """Estimate skew from the median angle of merged text-line blobs.

        Words are morphologically dilated into horizontal line blobs; each
        blob's minAreaRect angle votes, and the median wins. This is far more
        robust to noise than Hough lines on small or degraded text.
        """
        import cv2
        import numpy as np

        h, w = gray.shape[:2]
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Merge characters/words into full text-line blobs
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 40, 15), 3))
        merged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        merged = cv2.dilate(merged, kernel, iterations=1)

        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        angles = []
        for contour in contours:
            rect = cv2.minAreaRect(contour)
            (_, _), (rw, rh), angle = rect
            if rw < rh:
                rw, rh = rh, rw
                angle += 90.0
            # Only wide, line-like blobs vote (skip logos, stamps, noise specks)
            if rw < w / 8 or rh <= 0 or rw / rh < 4:
                continue
            # Normalize to [-45, 45]
            if angle > 45:
                angle -= 90
            elif angle < -45:
                angle += 90
            if abs(angle) <= MAX_SKEW_DEGREES:
                angles.append(angle)

        if len(angles) < 2:
            return 0.0
        return float(np.median(angles))

    @staticmethod
    def _rotate(gray, angle: float):
        """Rotate around center, expanding the canvas so nothing is cropped."""
        import cv2
        import numpy as np

        h, w = gray.shape[:2]
        center = (w / 2, h / 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

        cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
        new_w = int(h * sin + w * cos)
        new_h = int(h * cos + w * sin)
        matrix[0, 2] += (new_w / 2) - center[0]
        matrix[1, 2] += (new_h / 2) - center[1]

        return cv2.warpAffine(
            gray,
            matrix,
            (new_w, new_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    @staticmethod
    def _sharpen(gray):
        """Unsharp mask — gentler than a Laplacian kernel, no halo artifacts."""
        import cv2

        blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=2.0)
        return cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)

    @staticmethod
    def _adaptive_threshold(gray):
        """Optional binarization. Block size large enough to keep table lines."""
        import cv2

        return cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=35,
            C=11,
        )


def enhance_image(image_path: str, enabled: bool = True, binarize: bool | None = None) -> PreprocessResult:
    """Convenience entry point used by the OCR service.

    Reads `IMAGE_ENHANCE_BINARIZE` from Flask config / env when `binarize`
    is not explicitly provided.
    """
    if not enabled:
        return PreprocessResult(path=image_path, success=True, applied_steps=["disabled"])

    if binarize is None:
        binarize = _config_flag("IMAGE_ENHANCE_BINARIZE", False)

    return ImagePreprocessor(binarize=binarize).enhance(image_path)


def _config_flag(key: str, default: bool) -> bool:
    try:
        from flask import current_app

        value = current_app.config.get(key)
        if value is not None:
            return str(value).lower() == "true" if isinstance(value, str) else bool(value)
    except Exception:
        pass
    return str(os.getenv(key, str(default))).lower() == "true"
