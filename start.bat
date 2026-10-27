@echo off
REM AgentHub One-Command Starter for Windows Command Prompt
cd /d "%~dp0"


REM Check and auto-start Temporal container stack only if Docker is running
where docker >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    docker info >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [*] Docker active: ensuring Temporal container stack is started...
        docker compose up -d postgresql temporal temporal-ui >nul 2>&1
    )
)

REM Free port 8001 if a prior cancelled batch run left a lingering process
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8001 ^| findstr LISTENING 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo [*] Launching AgentHub Orchestrator and Worker Runner...
IF EXIST ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe run.py
) ELSE (
    python run.py
)

if %ERRORLEVEL% NEQ 0 (
    echo [!] AgentHub exited with code %ERRORLEVEL%.
)
