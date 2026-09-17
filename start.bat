@echo off
REM UAOS One-Command Starter for Windows Command Prompt

IF EXIST ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe run.py
) ELSE (
    python run.py
)
pause
