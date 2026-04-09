@echo off
chcp 65001 >nul
title Meridian

cd /d F:\VCPToolBox\wyckoff

echo ================================
echo   Meridian Starting...
echo ================================
echo.
echo Backend:  http://localhost:6100
echo Frontend: http://localhost:5173
echo.

netstat -ano 2>nul | findstr ":6100 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [Backend] Starting...
    start "Meridian Backend" cmd /k "cd /d F:\VCPToolBox\wyckoff && python -m uvicorn backend.main:app --host 0.0.0.0 --port 6100 --reload"
    echo [Backend] Waiting...
    timeout /t 3 >nul
) else (
    echo [Backend] Port 6100 already in use, skipping.
)

netstat -ano 2>nul | findstr ":5173 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [Frontend] Starting...
    start "Meridian Frontend" cmd /k "cd /d F:\VCPToolBox\wyckoff\frontend && npm run dev"
    echo [Frontend] Waiting...
    timeout /t 5 >nul
) else (
    echo [Frontend] Port 5173 already in use, skipping.
)

echo Opening browser...
start http://localhost:5173

echo ================================
echo   Done. Browser opened.
echo ================================
pause
