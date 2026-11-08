# VayuMitra — start the whole AI-PC stack (Windows PowerShell).
#   ./infra/scripts/run_all.ps1        # real devices on the LAN
#   ./infra/scripts/run_all.ps1 -Sim   # built-in simulator, no peripherals
#
# Starts: Mosquitto broker -> orchestrator -> Streamlit dashboard, each in its
# own window. PIDs are saved to infra/scripts/.pids for stop_all.ps1.
param(
    [switch]$Sim
)
$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "No .venv found — run ./infra/scripts/setup.ps1 first." -ForegroundColor Red
    exit 1
}

$PidFile = Join-Path $PSScriptRoot ".pids"
if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
$pids = @()

# --- LAN IP (for the phone + UNO Q) ---
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -First 1 -ExpandProperty IPAddress)
if (-not $lanIp) { $lanIp = "127.0.0.1" }

# --- 1. Mosquitto broker ---
Write-Host "Starting Mosquitto broker (:1883)..." -ForegroundColor Yellow
$mosqConf = Join-Path $Root "ai_pc\broker\mosquitto.conf"
$mosq = $null
try {
    $mosq = Start-Process -FilePath "mosquitto" -ArgumentList @("-c", $mosqConf, "-v") -PassThru -WindowStyle Normal
    $pids += $mosq.Id
} catch {
    Write-Host "  Could not launch 'mosquitto' (is it installed + on PATH?)." -ForegroundColor Red
    Write-Host "  Install: winget install EclipseFoundation.Mosquitto" -ForegroundColor Red
}
Start-Sleep -Seconds 2

# --- 2. Orchestrator ---
$orchArgs = @("-m", "ai_pc.orchestrator.main")
if ($Sim) { $orchArgs += "--sim" }
Write-Host "Starting orchestrator ($([string]::Join(' ', $orchArgs)))..." -ForegroundColor Yellow
$orch = Start-Process -FilePath $Py -ArgumentList $orchArgs -PassThru -WorkingDirectory $Root -WindowStyle Normal
$pids += $orch.Id
Start-Sleep -Seconds 2

# --- 3. Dashboard ---
Write-Host "Starting Streamlit dashboard (:8501)..." -ForegroundColor Yellow
$dashArgs = @("-m", "streamlit", "run", "ai_pc\dashboard\app.py",
              "--server.port", "8501", "--server.headless", "true")
$dash = Start-Process -FilePath $Py -ArgumentList $dashArgs -PassThru -WorkingDirectory $Root -WindowStyle Normal
$pids += $dash.Id

# --- save pids ---
$pids | Set-Content -Path $PidFile -Encoding utf8

Write-Host ""
Write-Host "==================== VayuMitra is up ====================" -ForegroundColor Green
Write-Host " Dashboard : http://localhost:8501"
Write-Host " API       : http://localhost:8000/state"
Write-Host " Broker    : $lanIp:1883"
Write-Host ""
Write-Host " On the PHONE and UNO Q, set MQTT_HOST = $lanIp" -ForegroundColor Cyan
if ($Sim) {
    Write-Host " SIM MODE: telemetry + spikes are simulated (no peripherals needed)." -ForegroundColor Cyan
} else {
    Write-Host " Now start the UNO Q app and the phone app (both pointing at $lanIp)." -ForegroundColor Cyan
    Write-Host " Laptop fallback publisher:  python uno_q/python/main.py --mock"
}
Write-Host " Stop everything:  ./infra/scripts/stop_all.ps1"
Write-Host "=========================================================" -ForegroundColor Green
