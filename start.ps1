# AgentHub One-Command Starter for Windows PowerShell

$ErrorActionPreference = "Stop"

Write-Host "Checking Python environment..." -ForegroundColor Cyan

# Optional: Auto-start Temporal and Web UI (ports 7234 & 8234) if Docker is present
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "[*] Checking Temporal container stack on Docker..." -ForegroundColor Cyan
    try {
        docker compose up -d postgresql temporal temporal-ui 2>$null
    } catch {}
}

# Check if .venv exists
if (Test-Path ".venv\Scripts\python.exe") {
    & .venv\Scripts\python.exe run.py
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python run.py
} else {
    Write-Host "Error: Python not found. Please install Python 3.11+." -ForegroundColor Red
    exit 1
}
