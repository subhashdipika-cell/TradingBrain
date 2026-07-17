@echo off
title TradingBrain Launcher
echo ============================================
echo   Starting TradingBrain
echo ============================================

REM --- Backend (FastAPI on port 8200) ---
REM NO --reload here: the reloader watches the whole backend tree, and the
REM AutoTrader/results write JSON state files inside it — each write restarted
REM the process and KILLED the in-flight forward-test thread (this silently
REM ended the 2026-07-17 auto run seconds after its 10:21 launch). Use
REM start_TradingBrain_dev.bat when actively developing.
cd /d "%~dp0backend"
start "TradingBrain Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8200"

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
