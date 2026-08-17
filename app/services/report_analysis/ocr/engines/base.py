"""Base OCR engine interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EngineLine:
    """Single OCR line with geometry and confidence."""

    text: str
    confidence: float
    box: list[list[float]] | None = None


@dataclass
class EngineOutput:
    """Raw OCR engine output before reading-order merge."""

    lines: list[EngineLine]
    engine_name: str


class BaseOCREngine(ABC):
    """Abstract OCR engine."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the engine can run in the current environment."""

    @abstractmethod
    def extract(self, image_path: str) -> EngineOutput:
        """Extract text and geometry from an image file."""
