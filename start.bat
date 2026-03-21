@echo off
title Wyckoff Trading Engine

echo.
echo ============================================================
echo   WYCKOFF TRADING ENGINE v2.0
echo ============================================================
echo.
echo   [1] Full Mode (API + Web)
echo   [2] API Server Only
echo   [3] Web Frontend Only
echo   [4] Trading System
echo   [5] Evolution System
echo.
set /p choice=Select [1-5]: 

if "%choice%"=="1" goto full_mode
if "%choice%"=="2" goto api_mode
if "%choice%"=="3" goto web_mode
if "%choice%"=="4" goto trading_mode
if "%choice%"=="5" goto evolution_mode
echo Invalid choice
pause
exit /b

:full_mode
echo.
echo Starting Full Mode (API + Web)...
start "Wyckoff API" python run.py --mode=api --port=9527
ping -n 4 127.0.0.1 >nul
start "Wyckoff Web" python -c "import subprocess; subprocess.run(['npm', 'run', 'dev'], cwd='frontend')"
echo.
echo   API: http://localhost:9527
echo   Web: http://localhost:5173
echo.
pause
exit /b

:api_mode
echo.
echo Starting API Server...
python run.py --mode=api --port=9527
pause
exit /b

:web_mode
echo.
echo Starting Web Frontend...
cd frontend
npm run dev
pause
exit /b

:trading_mode
echo.
echo Starting Trading System...
python run.py --mode=trading
pause
exit /b

:evolution_mode
echo.
echo Starting Evolution System...
python run_evolution.py
pause
exit /b
