# VayuMitra — one-time setup (Windows PowerShell).
# Creates a venv, installs deps + the contract, and seeds .env.
#
#   ./infra/scripts/setup.ps1
#
$ErrorActionPreference = "Stop"

# repo root = two levels up from this script
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root
Write-Host "VayuMitra setup in $Root" -ForegroundColor Cyan

# 1. venv
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
}
$Py = Join-Path $Root ".venv\Scripts\python.exe"

# 2. deps
Write-Host "Upgrading pip..." -ForegroundColor Yellow
& $Py -m pip install --upgrade pip

Write-Host "Installing AI-PC requirements..." -ForegroundColor Yellow
& $Py -m pip install -r ai_pc\requirements.txt

Write-Host "Installing the contract package (editable)..." -ForegroundColor Yellow
& $Py -m pip install -e packages\contract

# 3. .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example — edit MQTT_HOST for the LAN." -ForegroundColor Green
} else {
    Write-Host ".env already exists (left as-is)." -ForegroundColor Green
}

Write-Host ""
Write-Host "==================== NEXT STEPS ====================" -ForegroundColor Cyan
Write-Host "1. Install Mosquitto:   winget install EclipseFoundation.Mosquitto"
Write-Host "2. (NPU, on Surface):   .\.venv\Scripts\python -m pip install onnxruntime-qnn"
Write-Host "3. (LLM, optional):     winget install Microsoft.FoundryLocal"
Write-Host "                        .\.venv\Scripts\python -m pip install foundry-local-sdk-winml openai"
Write-Host "4. Set MQTT_HOST in .env to this PC's LAN IP (run: ipconfig)"
Write-Host "5. Run the stack:       ./infra/scripts/run_all.ps1 -Sim   (demo, no hardware)"
Write-Host "                        ./infra/scripts/run_all.ps1        (real devices)"
Write-Host "6. Run tests:           .\.venv\Scripts\python -m pytest -q"
Write-Host "====================================================" -ForegroundColor Cyan
