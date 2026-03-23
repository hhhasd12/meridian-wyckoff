@echo off
title Wyckoff Engine v3.0

echo.
echo ============================================================
echo   Wyckoff Trading Engine v3.0
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

:: Kill any leftover process on port 9527
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :9527 ^| findstr LISTENING') do (
    echo [CLEANUP] Killing leftover process on port 9527 (PID: %%a)
    taskkill /F /PID %%a >nul 2>&1
)

:: Build frontend if needed
if not exist "frontend\dist\index.html" (
    echo [BUILD] Frontend not built, building now...
    echo.
    cd frontend
    call npm install --silent 2>nul
    call npm run build
    cd ..
    echo.
    if not exist "frontend\dist\index.html" (
        echo [ERROR] Frontend build failed
        pause
        exit /b 1
    )
    echo [OK] Frontend build complete
    echo.
)

:: Start server (browser opens automatically)
echo [START] Launching server...
echo.
echo   URL: http://localhost:9527
echo   Browser will open automatically
echo   Press Ctrl+C to stop
echo.
python run.py --mode=api --port=9527

pause
