@echo off
REM UAOS One-Command Starter for Windows Command Prompt

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
