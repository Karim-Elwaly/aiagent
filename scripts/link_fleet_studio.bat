@echo off
REM Links or copies Fleet Studio into AgentHub workspace as 'frontend'
cd /d "%~dp0\.."

if not exist "frontend" (
    echo [*] Creating junction: D:\projects\aiagent\frontend -^> D:\projects\fleet studio
    mklink /J "frontend" "D:\projects\fleet studio" >nul 2>&1
    if exist "frontend\package.json" (
        echo [OK] Junction established successfully!
    ) else (
        echo [*] Junction not supported, copying project files with robocopy...
        robocopy "D:\projects\fleet studio" "frontend" /E /XD node_modules .next .git dist /XF .env.local
        echo [OK] Project copied to D:\projects\aiagent\frontend!
    )
) else (
    echo [OK] 'frontend' directory already exists in D:\projects\aiagent
)
