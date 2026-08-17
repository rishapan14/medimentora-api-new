# Start MediMentora API using the project virtual environment.
# Always use this script so OCR packages resolve correctly.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: .venv not found. Create it first:" -ForegroundColor Red
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

Write-Host "Starting MediMentora API with:" -ForegroundColor Cyan
Write-Host "  $venvPython"
Write-Host ""

& $venvPython -c @"
import importlib, sys
print('Python :', sys.executable)
checks = [
    ('rapidocr-onnxruntime', 'rapidocr_onnxruntime'),
    ('opencv-python', 'cv2'),
    ('numpy', 'numpy'),
    ('pymupdf', 'fitz'),
    ('pillow', 'PIL'),
]
missing = []
for label, mod in checks:
    try:
        importlib.import_module(mod)
        print(f'  PASS {label}')
    except Exception:
        print(f'  FAIL {label}')
        missing.append(label)
if missing:
    print('')
    print('OCR packages missing. Install with:')
    print(r'  .\.venv\Scripts\python.exe -m pip install ' + ' '.join(missing))
    raise SystemExit(1)
print('OCR packages ready')
"@

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Launching run.py ..." -ForegroundColor Green
& $venvPython run.py
