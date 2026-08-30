@echo off
REM TradingBrain - TB007 weekly backtest tracker
REM Reruns TB007 across all accumulated Dhan option-chain data and appends a
REM dated read to the Trading_Mind wiki. Registered as a weekly Task Scheduler
REM job (see docs/tb007-scheduler.md). Safe to run manually any time.
title TB007 Weekly Backtest
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] TradingBrain backend Python environment is missing.
  exit /b 1
)
if not exist "scripts\logs" mkdir "scripts\logs"
echo ==== %DATE% %TIME% ==== >> "scripts\logs\tb007_report.log"
.venv\Scripts\python.exe -m scripts.tb007_backtest_report >> "scripts\logs\tb007_report.log" 2>&1
set "REPORT_EXIT=%ERRORLEVEL%"
if not "%REPORT_EXIT%"=="0" echo [ERROR] TB007 report failed with exit code %REPORT_EXIT%. See scripts\logs\tb007_report.log.
exit /b %REPORT_EXIT%
