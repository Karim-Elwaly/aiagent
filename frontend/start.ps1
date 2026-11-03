# Fleet Studio — One-Command Independent Launcher for PowerShell
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Determine python executable: use backend venv if present, otherwise system python
$PythonExe = "python"
if (Test-Path "$ScriptDir\backend\.venv\Scripts\python.exe") {
    $PythonExe = "$ScriptDir\backend\.venv\Scripts\python.exe"
}

Write-Host "[*] Starting Fleet Studio Backend on port 8001..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ScriptDir\backend'; & '$PythonExe' -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload"

Write-Host "[*] Starting Fleet Studio Frontend on port 3000..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ScriptDir\frontend'; npm run dev"

Write-Host ""
Write-Host "====================================================" -ForegroundColor Green
Write-Host "  Fleet Studio is launching!" -ForegroundColor Green
Write-Host "  Web UI:    http://localhost:3000" -ForegroundColor Green
Write-Host "  Backend:   http://localhost:8001" -ForegroundColor Green
Write-Host "  API Docs:  http://localhost:8001/docs" -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green
