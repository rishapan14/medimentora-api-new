import sys
from pathlib import Path

from app import create_app


def _print_ocr_startup_status() -> None:
  """Print OCR readiness so environment mismatches are obvious at boot."""
  python_path = Path(sys.executable)
  in_venv = ".venv" in str(python_path).lower() or hasattr(sys, "real_prefix") or (
    hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
  )
  env_label = ".venv" if ".venv" in str(python_path).lower() else ("venv" if in_venv else "global")

  engine_name = "none"
  version = "n/a"
  ready = False
  try:
    from app.services.report_analysis.ocr.engines.paddle_engine import PaddleOCREngine

    engine = PaddleOCREngine()
    ready = engine.is_available()
    if ready:
      engine_name = "RapidOCR (PaddleOCR ONNX)"
      try:
        import rapidocr_onnxruntime as rapid

        version = getattr(rapid, "__version__", "installed")
      except Exception:
        version = "installed"
  except Exception as exc:
    engine_name = f"error: {exc}"

  mark = "OK" if ready else "FAIL"
  print(f"[{mark}] OCR Engine : {engine_name}")
  print(f"[{mark}] Version    : {version}")
  print(f"[{mark}] Python     : {env_label} ({python_path})")
  print(f"[{mark}] Ready      : {ready}")
  if not ready:
    print(
      "HINT: Start the API with .venv so OCR packages resolve:\n"
      "  .\\.venv\\Scripts\\python.exe run.py\n"
      "  or .\\start-api.ps1"
    )


app = create_app()

if __name__ == "__main__":
  # The production start command runs this before Gunicorn. Keep direct local
  # execution convenient without running DDL during WSGI module import.
  from app.schema_bootstrap import bootstrap_schema

  bootstrap_schema(app)
  _print_ocr_startup_status()
  app.run(
    debug=app.config["FLASK_DEBUG"],
    port=int(__import__("os").getenv("PORT", "5000")),
  )
