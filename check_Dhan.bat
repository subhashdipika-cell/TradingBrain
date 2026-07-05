@echo off
title TradingBrain Dhan Preflight
echo Running Dhan connectivity check...
echo.
set SYMBOL=%1
if "%SYMBOL%"=="" set SYMBOL=NIFTY
cd /d "%~dp0backend"
.venv\Scripts\python.exe -m app.application.check_dhan --symbol %SYMBOL%
echo.
pause
