# Download, clean, enrich, and load live Canadian grants data.
# Usage:
#   .\scripts\run_pipeline.ps1
#   $env:FORCE_INGEST = "1"; .\scripts\run_pipeline.ps1   # re-download raw files
#   $env:SKIP_INGEST = "1"; .\scripts\run_pipeline.ps1      # reuse data/raw cache

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

$env:PYTHONPATH = "pipeline"
python pipeline/run_all.py
