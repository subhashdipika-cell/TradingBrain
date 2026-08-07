@echo off
title TradingBrain Launcher
echo ============================================
echo   Starting TradingBrain
echo ============================================

REM --- Backend (FastAPI on port 8200) ---
cd /d "%~dp0backend"
start "TradingBrain Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8200 --reload"

REM --- Frontend (Vite dev server on port 5174) ---
cd /d "%~dp0frontend"
start "TradingBrain Frontend" cmd /k "npm run dev"

echo.
echo   Backend  : http://localhost:8200   (API docs at /docs)
echo   Frontend : http://localhost:5174
echo.
echo Waiting for the frontend to come up...
timeout /t 5 >nul
start "" http://localhost:5174
echo Launched. Use close_TradingBrain.bat to stop.
