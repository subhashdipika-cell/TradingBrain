@echo off
title TradingBrain Shutdown
echo ============================================
echo   Stopping TradingBrain
echo ============================================

REM --- Kill whatever is listening on the app ports (8200 backend, 5174 frontend) ---
for %%P in (8200 5174) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%%P ^| findstr LISTENING') do (
    echo Stopping process on port %%P (PID %%a)
    taskkill /F /PID %%a >nul 2>&1
  )
)

REM --- Close the launcher console windows by title (fallback) ---
taskkill /F /FI "WINDOWTITLE eq TradingBrain Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq TradingBrain Frontend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq TradingBrain Forward Paper*" >nul 2>&1

echo Done.
timeout /t 2 >nul
