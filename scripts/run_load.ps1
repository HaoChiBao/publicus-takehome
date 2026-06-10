# Upload processed CSV/JSON checkpoints to Supabase (~30-60 min for full awards).
# Progress bars print to stderr during upload.
# Usage:
#   .\scripts\run_load.ps1                                    # full recompute + upload
#   $env:LOAD_UPLOAD_ONLY = "1"; .\scripts\run_load.ps1       # fast restore from cached files
#   $env:SKIP_AWARDS = "1"; .\scripts\run_load.ps1            # programs + recipients only (~5 min)
#   $env:LOAD_AWARDS_ONLY = "1"; .\scripts\run_load.ps1       # awards only (~30-60 min)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

$env:PYTHONPATH = "pipeline"
Write-Host "Uploading to Supabase via DATABASE_URL (this may take 30-60 minutes)..."
python pipeline/load.py
