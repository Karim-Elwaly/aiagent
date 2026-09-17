# PowerShell script to initialize, commit, and push to GitHub
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Pushing UAOS changes to https://github.com/Karim-Elwaly/aiagent" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path ".git")) {
    Write-Host "[*] Initializing Git repository..." -ForegroundColor Yellow
    git init
    git branch -M main
    git remote add origin https://github.com/Karim-Elwaly/aiagent.git
} else {
    Write-Host "[*] Git repository already initialized." -ForegroundColor Green
    git remote set-url origin https://github.com/Karim-Elwaly/aiagent.git 2>$null
    if ($LASTEXITCODE -ne 0) {
        git remote add origin https://github.com/Karim-Elwaly/aiagent.git
    }
}

Write-Host "[*] Staging files..." -ForegroundColor Yellow
git add .

Write-Host "[*] Committing changes..." -ForegroundColor Yellow
git commit -m "feat: implement Agent Studio, Reusable Agents, and AI Skill Builder"

Write-Host "[*] Pushing to GitHub (main)..." -ForegroundColor Yellow
git push -u origin main

Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Successfully completed!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
