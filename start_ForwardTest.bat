@echo off
title TradingBrain Forward Test
echo ============================================
echo   TradingBrain Forward Test (Dhan, paper)
echo ============================================
echo Connects to Dhan, polls the LIVE option chain during market hours,
echo runs the regime-selected strategies with simulated fills (no capital
echo at risk), and saves the result to the analysis page.
echo.
set SYMBOL=%1
if "%SYMBOL%"=="" set SYMBOL=NIFTY
cd /d "%~dp0backend"
.venv\Scripts\python.exe -m app.application.forward_test --symbol %SYMBOL%
echo.
echo Forward test finished. Open the dashboard Analysis tab to review.
pause
