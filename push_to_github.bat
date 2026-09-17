@echo off
echo ============================================================
echo   Pushing UAOS changes to https://github.com/Karim-Elwaly/aiagent
echo ============================================================

REM 1. Initialize git if not already initialized
if not exist ".git" (
    echo [*] Initializing Git repository...
    git init
    git branch -M main
    git remote add origin https://github.com/Karim-Elwaly/aiagent.git
) else (
    echo [*] Git repository already initialized.
    git remote set-url origin https://github.com/Karim-Elwaly/aiagent.git 2>nul || git remote add origin https://github.com/Karim-Elwaly/aiagent.git
)

REM 2. Stage all files
echo [*] Staging files...
git add .

REM 3. Commit
echo [*] Committing changes...
git commit -m "feat: implement Agent Studio, Reusable Agents, and AI Skill Builder"

REM 4. Push to remote
echo [*] Pushing to GitHub...
git push -u origin main

echo ============================================================
echo   Done!
echo ============================================================
pause
