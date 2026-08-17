"""Optional Azure Document Intelligence OCR provider (stub/integration hook)."""

from __future__ import annotations

import logging
import os

from app.services.report_analysis.ocr.engines.base import BaseOCREngine, EngineLine, EngineOutput

logger = logging.getLogger(__name__)


class AzureDocumentIntelligenceEngine(BaseOCREngine):
    """Azure AI Document Intelligence — enable with AZURE_DOCUMENT_INTELLIGENCE_* env vars."""

    name = "azure_document_intelligence"

    def is_available(self) -> bool:
        return bool(os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") and os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY"))

    def extract(self, image_path: str) -> EngineOutput:
        if not self.is_available():
            raise RuntimeError("Azure Document Intelligence is not configured.")

        try:
            from azure.ai.formrecognizer import DocumentAnalysisClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise RuntimeError("Install azure-ai-formrecognizer to use Azure Document Intelligence.") from exc

        endpoint = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
        key = os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]
        client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))

        with open(image_path, "rb") as f:
            poller = client.begin_analyze_document("prebuilt-read", document=f)
        result = poller.result()
        text = result.content or ""
        logger.info("Azure Document Intelligence OCR completed (%d chars)", len(text))
        lines = [EngineLine(text=line, confidence=0.9) for line in text.splitlines() if line.strip()]
        return EngineOutput(lines=lines, engine_name=self.name)
