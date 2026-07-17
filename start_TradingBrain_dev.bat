@echo off
title TradingBrain Launcher (DEV)
echo ============================================
echo   Starting TradingBrain  (DEV - hot reload)
echo ============================================
echo   WARNING: --reload restarts the backend on ANY file change in backend/,
echo   including the AutoTrader/results JSON state writes - which KILLS an
echo   in-flight forward test. Never use this during market hours.
echo ============================================

REM --- Backend (FastAPI on port 8200, hot reload, .py files only) ---
cd /d "%~dp0backend"
start "TradingBrain Backend (DEV)" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8200 --reload --reload-include *.py"

REM --- Frontend (Vite dev server on port 5174) ---
cd /d "%~dp0frontend"
start "TradingBrain Frontend" cmd /k "npm run dev"
