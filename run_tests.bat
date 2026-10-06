@echo off
REM Run Full PyTest Suite for UAOS
echo [*] Running UAOS PyTest Suite...
IF EXIST ".venv\Scripts\pytest.exe" (
    .venv\Scripts\pytest.exe tests\unit\ -v
) ELSE (
    python -m pytest tests\unit\ -v
)
pause
