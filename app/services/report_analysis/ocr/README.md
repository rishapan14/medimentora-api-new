# Module 1 — OCR Pipeline

Production OCR service for MediMentora medical report analysis.

## Architecture

```
app/services/report_analysis/ocr/
├── service.py              # OCRService orchestrator
├── models.py               # OCRResult, OCRQualityMetrics
├── preprocessing.py        # Orientation, contrast, denoise, upscale
├── text_cleaner.py         # OCR error fixes, dedupe, lab line preservation
├── reading_order.py        # Multi-column reading order merge
├── pdf_extractor.py        # Digital PDF + scanned page OCR (PyMuPDF)
└── engines/
    ├── paddle_engine.py    # PaddleOCR via RapidOCR ONNX (default)
    ├── tesseract_engine.py
    ├── google_document_ai.py   # Optional cloud
    └── azure_document_intelligence.py  # Optional cloud
```

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OCR_ENGINE` | `auto` | `auto`, `paddleocr`, `tesseract`, `google_document_ai`, `azure_document_intelligence` |
| `OCR_PREPROCESS` | `true` | Image enhancement before OCR |
| `OCR_TIMEOUT_SECONDS` | `120` | Per-page timeout |

## API response fields (extract endpoint)

- `ocr_engine` — engine used
- `ocr_quality.confidence` — 0–1 quality score
- `processing_time_ms` — pipeline duration
- `pages[]` — per-page metadata (PDF)

## Install

```bash
pip install -r requirements.txt
```

Restart API after changing OCR settings.
