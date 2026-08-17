"""Optional Google Document AI OCR provider (stub/integration hook)."""

from __future__ import annotations

import logging
import os

from app.services.report_analysis.ocr.engines.base import BaseOCREngine, EngineLine, EngineOutput

logger = logging.getLogger(__name__)


class GoogleDocumentAIEngine(BaseOCREngine):
    """Google Cloud Document AI — enable with GOOGLE_DOCUMENT_AI_* env vars."""

    name = "google_document_ai"

    def is_available(self) -> bool:
        return bool(
            os.getenv("GOOGLE_DOCUMENT_AI_PROJECT_ID")
            and os.getenv("GOOGLE_DOCUMENT_AI_PROCESSOR_ID")
            and os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )

    def extract(self, image_path: str) -> EngineOutput:
        if not self.is_available():
            raise RuntimeError("Google Document AI is not configured.")

        try:
            from google.cloud import documentai_v1 as documentai
        except ImportError as exc:
            raise RuntimeError("Install google-cloud-documentai to use Google Document AI.") from exc

        project_id = os.environ["GOOGLE_DOCUMENT_AI_PROJECT_ID"]
        location = os.getenv("GOOGLE_DOCUMENT_AI_LOCATION", "us")
        processor_id = os.environ["GOOGLE_DOCUMENT_AI_PROCESSOR_ID"]

        client = documentai.DocumentProcessorServiceClient()
        name = client.processor_path(project_id, location, processor_id)

        with open(image_path, "rb") as f:
            raw = f.read()

        mime = "application/pdf" if image_path.lower().endswith(".pdf") else "image/png"
        request = documentai.ProcessRequest(
            name=name,
            raw_document=documentai.RawDocument(content=raw, mime_type=mime),
        )
        result = client.process_document(request=request)
        text = result.document.text or ""
        logger.info("Google Document AI OCR completed (%d chars)", len(text))
        lines = [EngineLine(text=line, confidence=0.9) for line in text.splitlines() if line.strip()]
        return EngineOutput(lines=lines, engine_name=self.name)
