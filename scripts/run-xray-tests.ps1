# Run X-ray Module 11 test suite
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = $root
& "$root\.venv\Scripts\python.exe" -m pytest tests/ -v --tb=short
