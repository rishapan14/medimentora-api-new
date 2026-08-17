"""Phase 18 — X-ray OpenAPI / Swagger UI (no flasgger dependency).

Serves ``docs/openapi-xray.yaml`` and an interactive Swagger UI at ``/apidocs``.
Scope is X-ray APIs only (student + admin monitor/reference), not the full platform.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, send_file

docs_bp = Blueprint("xray_docs", __name__)

_SPEC_REL = Path("docs") / "openapi-xray.yaml"


def _spec_path() -> Path:
  root = Path(current_app.root_path).parent
  return root / _SPEC_REL


@docs_bp.get("/apispec/xray.yaml")
def openapi_xray_yaml():
  """Raw OpenAPI 3 YAML for X-ray endpoints."""
  path = _spec_path()
  if not path.is_file():
    return jsonify({"status": "error", "message": "OpenAPI spec not found."}), 404
  return send_file(
    path,
    mimetype="application/yaml",
    as_attachment=False,
    download_name="openapi-xray.yaml",
  )


@docs_bp.get("/apispec/xray")
@docs_bp.get("/apispec/xray.json")
def openapi_xray_meta():
  """Lightweight JSON pointer to the YAML spec + safety notes."""
  from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER, XRAY_SHORT_DISCLAIMER
  from app.services.xray.evaluation import SAFETY

  path = _spec_path()
  return jsonify(
    {
      "status": "success",
      "message": "MediMentora X-ray OpenAPI (Phase 18)",
      "data": {
        "openapi": "3.0.3",
        "title": "MediMentora AI X-Ray Analysis API",
        "spec_url": "/apispec/xray.yaml",
        "swagger_ui": "/apidocs",
        "scope": "xray_only",
        "short_disclaimer": XRAY_SHORT_DISCLAIMER,
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
        "evaluation_safety": SAFETY,
        "spec_present": path.is_file(),
      },
    }
  )


@docs_bp.get("/apidocs")
@docs_bp.get("/apidocs/")
def swagger_ui():
  """Interactive Swagger UI (CDN) for the X-ray OpenAPI spec."""
  html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MediMentora X-Ray API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css" />
  <style>
    body { margin: 0; background: #fafafa; }
    .mm-banner {
      font-family: Georgia, "Times New Roman", serif;
      background: #1a2332;
      color: #f0ebe3;
      padding: 0.85rem 1.25rem;
      font-size: 0.9rem;
      line-height: 1.45;
      border-bottom: 3px solid #c4a35a;
    }
    .mm-banner strong { color: #c4a35a; }
  </style>
</head>
<body>
  <div class="mm-banner">
    <strong>Educational only.</strong>
    X-ray AI endpoints are for learning and decision-support — not diagnosis.
    Admin evaluation metrics are monitoring proxies, not clinical accuracy.
  </div>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/apispec/xray.yaml",
      dom_id: "#swagger-ui",
      deepLinking: true,
      presets: [SwaggerUIBundle.presets.apis],
      layout: "BaseLayout",
      persistAuthorization: true,
    });
  </script>
</body>
</html>
"""
  return Response(html, mimetype="text/html; charset=utf-8")
