@echo off
REM UAOS One-Command Starter for Windows Command Prompt

REM Attempt to start Temporal dev server container via Docker Compose
docker compose up -d temporal >nul 2>&1

:loop
echo [*] Launching UAOS Orchestrator and Worker Runner...
IF EXIST ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe run.py
) ELSE (
    python run.py
)
echo [!] UAOS stopped. Restarting in 2 seconds... (Press Ctrl+C to stop)
timeout /t 2
goto loop
