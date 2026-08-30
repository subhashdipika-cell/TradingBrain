@echo off
setlocal EnableExtensions
title TradingBrain Launcher
echo ============================================
echo   Starting TradingBrain
echo ============================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "LOGDIR=%ROOT%work\launcher-logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

if not exist "%BACKEND%\.venv\Scripts\python.exe" (
  echo [ERROR] TradingBrain backend environment is missing.
  exit /b 1
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm.cmd is not available in PATH.
  exit /b 1
)

set "BACKEND_STATE=missing"
powershell.exe -NoLogo -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8200 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if(-not $c){exit 2}; $cmd=(Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" -ErrorAction SilentlyContinue).CommandLine; if($cmd -match 'TradingBrain.+uvicorn app[.]main:app'){exit 0}; exit 1" >nul 2>&1
if not errorlevel 1 set "BACKEND_STATE=ready"
if errorlevel 1 if not errorlevel 2 set "BACKEND_STATE=conflict"

set "FRONTEND_STATE=missing"
powershell.exe -NoLogo -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if(-not $c){exit 2}; $cmd=(Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" -ErrorAction SilentlyContinue).CommandLine; if($cmd -match 'TradingBrain.+vite'){exit 0}; exit 1" >nul 2>&1
if not errorlevel 1 set "FRONTEND_STATE=ready"
if errorlevel 1 if not errorlevel 2 set "FRONTEND_STATE=conflict"

if "%BACKEND_STATE%"=="conflict" (
  echo [ERROR] Port 8200 belongs to another application. Nothing was stopped.
  exit /b 1
)
if "%FRONTEND_STATE%"=="conflict" (
  echo [ERROR] Port 5174 belongs to another application. Nothing was stopped.
  exit /b 1
)

REM --- Backend (FastAPI on port 8200) ---
REM NO --reload here: the reloader watches the whole backend tree, and the
REM AutoTrader/results write JSON state files inside it — each write restarted
REM the process and KILLED the in-flight forward-test thread (this silently
REM ended the 2026-07-17 auto run seconds after its 10:21 launch). Use
REM start_TradingBrain_dev.bat when actively developing.
if "%BACKEND_STATE%"=="ready" (
  echo [READY] Reusing the TradingBrain backend on port 8200.
) else if /i "%TRADING_LAB_HIDDEN%"=="1" (
  start "" /b "%BACKEND%\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir "%BACKEND%" --host 127.0.0.1 --port 8200 1^>^>"%LOGDIR%\backend.log" 2^>^&1
) else (
  start "TradingBrain Backend" cmd.exe /k "cd /d ""%BACKEND%"" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8200"
)

REM --- Frontend (Vite dev server on port 5174) ---
if "%FRONTEND_STATE%"=="ready" (
  echo [READY] Reusing the TradingBrain frontend on port 5174.
) else if /i "%TRADING_LAB_HIDDEN%"=="1" (
  start "" /b cmd.exe /d /c "cd /d ""%FRONTEND%"" && npm.cmd run dev 1^>^>""%LOGDIR%\frontend.log"" 2^>^&1"
) else (
  start "TradingBrain Frontend" cmd.exe /k "cd /d ""%FRONTEND%"" && npm.cmd run dev"
)

echo.
echo   Backend  : http://localhost:8200   (API docs at /docs)
echo   Frontend : http://localhost:5174
echo.
echo Waiting for the frontend to come up...
powershell.exe -NoLogo -NoProfile -Command "$deadline=(Get-Date).AddSeconds(60); do { try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5174/' -TimeoutSec 2; if($r.StatusCode -eq 200){Start-Process 'http://127.0.0.1:5174/'; exit 0} } catch {}; Start-Sleep -Milliseconds 500 } while((Get-Date)-lt $deadline); exit 1"
if errorlevel 1 (
  echo [ERROR] TradingBrain frontend did not become ready within 60 seconds.
  exit /b 1
)
echo Launched. Use close_TradingBrain.bat to stop.
endlocal
