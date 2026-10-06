@echo off
REM One-Click Verification Harness for UAOS
echo [*] Running UAOS Automated Verification Suite...
IF EXIST ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe tests\verify_all.py
) ELSE (
    python tests\verify_all.py
)
pause
