@echo off
REM AgentHub One-Command Starter for Windows Command Prompt

REM Check and automatically start Temporal container stack (Postgres + Server + Web UI on 8234)
where docker >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [*] Checking Docker and auto-starting Temporal Web UI stack...
    docker compose up -d postgresql temporal temporal-ui >nul 2>&1
)

:loop
echo [*] Launching AgentHub Orchestrator and Worker Runner...
IF EXIST ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe run.py
) ELSE (
    python run.py
)
echo [!] AgentHub stopped. Restarting in 2 seconds... (Press Ctrl+C to stop)
timeout /t 2
goto loop
