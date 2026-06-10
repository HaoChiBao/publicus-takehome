# Start the FastAPI backend (reads from Supabase when DATABASE_URL is set).
# Usage:
#   .\scripts\run_api.ps1
#   .\scripts\run_api.ps1 -Port 8001

param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

# Free the port if another local API instance is still running.
$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($connections) {
    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $name = if ($proc) { $proc.ProcessName } else { "unknown" }
        Write-Host "Port $Port is in use by $name (PID $procId) - stopping it so the API can start."
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

Set-Location api
$url = "http://127.0.0.1:$Port"
Write-Host "Starting API at $url"
python -m uvicorn main:app --reload --host 127.0.0.1 --port $Port
