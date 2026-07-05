@echo off
title TradingBrain Forward Test - TB008 Calendar
echo ============================================
echo   TB008 Adaptive Calendar Spread - Forward Test
echo ============================================
echo Sells a far-OTM (~2-delta) strangle on the NEAR expiry and hedges with a
echo next-expiry ratio calendar (both chains pulled live from Dhan). Simulated
echo fills, no capital at risk. Banks ~1%% of margin then exits.
echo.
echo Note: the calendar's margin is ~Rs 2L per structure, so this runs with
echo Rs 10,00,000 capital by default (edit --capital below to change).
echo.
set SYMBOL=%1
if "%SYMBOL%"=="" set SYMBOL=NIFTY
cd /d "%~dp0backend"
.venv\Scripts\python.exe -m app.application.forward_test --symbol %SYMBOL% --strategy TB008 --capital 1000000
echo.
echo Forward test finished. Open the dashboard Analysis tab to review.
pause
