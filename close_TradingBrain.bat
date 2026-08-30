@echo off
title TradingBrain Shutdown
echo ============================================
echo   Stopping TradingBrain
echo ============================================

REM Stop only listeners whose command line identifies this TradingBrain checkout.
REM An unrelated service using one of these ports is reported and preserved.
powershell.exe -NoLogo -NoProfile -Command ^
  "$stopped=0;" ^
  "foreach($port in 8200,5174){" ^
  "  $listeners=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue;" ^
  "  foreach($listener in $listeners){" ^
  "    $proc=Get-CimInstance Win32_Process -Filter \"ProcessId=$($listener.OwningProcess)\" -ErrorAction SilentlyContinue;" ^
  "    if($proc.CommandLine -match 'D:[\\/]Projects[\\/]TradingBrain' -and $proc.CommandLine -match 'uvicorn|vite'){" ^
  "      Write-Host \"Stopping TradingBrain process on port $port (PID $($proc.ProcessId))\";" ^
  "      Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue; $stopped++" ^
  "    } else { Write-Warning \"Port $port is owned by another application; it was not stopped.\" }" ^
  "  }" ^
  "};" ^
  "if($stopped -eq 0){Write-Host 'No running TradingBrain listeners were found.'}"

echo Done.
if /i not "%TRADING_LAB_HIDDEN%"=="1" timeout /t 2 >nul
