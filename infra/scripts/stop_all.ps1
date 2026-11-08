# VayuMitra — stop the processes started by run_all.ps1.
#   ./infra/scripts/stop_all.ps1
$ErrorActionPreference = "Continue"

$PidFile = Join-Path $PSScriptRoot ".pids"
if (Test-Path $PidFile) {
    Get-Content $PidFile | ForEach-Object {
        $procId = $_.Trim()
        if ($procId) {
            try {
                Stop-Process -Id ([int]$procId) -Force -ErrorAction Stop
                Write-Host "stopped PID $procId" -ForegroundColor Yellow
            } catch {
                Write-Host "PID $procId already gone" -ForegroundColor DarkGray
            }
        }
    }
    Remove-Item $PidFile -Force
} else {
    Write-Host "No .pids file; attempting best-effort cleanup by name..." -ForegroundColor Yellow
    Get-Process mosquitto -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
Write-Host "done." -ForegroundColor Green
