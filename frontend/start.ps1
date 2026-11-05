# Fleet Studio — One-Command Independent Launcher for PowerShell
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Determine python executable: prefer a virtualenv that can actually import the
# Fleet Studio backend dependencies, then fall back to system python.
$PythonCandidates = @(
    "$ScriptDir\..\.venv\Scripts\python.exe",
    "$ScriptDir\backend\.venv\Scripts\python.exe",
    "python"
)
$PythonExe = "python"
foreach ($Candidate in $PythonCandidates) {
    if ($Candidate -ne "python" -and -not (Test-Path $Candidate)) { continue }
    & $Candidate -c "import sqlalchemy, fastapi, uvicorn, aiosqlite, jsonschema" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $PythonExe = $Candidate
        break
    }
}
if ($PythonExe -eq "python") {
    & python -c "import sqlalchemy, fastapi, uvicorn, aiosqlite, jsonschema" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] No Python environment with Fleet Studio backend dependencies found." -ForegroundColor Yellow
        Write-Host "    Install with: python -m pip install -e `"$ScriptDir\backend[dev]`"" -ForegroundColor Yellow
    }
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
