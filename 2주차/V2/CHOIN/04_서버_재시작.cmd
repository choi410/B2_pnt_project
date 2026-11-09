@echo off
cd /d "%~dp0"
echo [1/2] Stopping the old server on port 8771 ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-NetTCPConnection -LocalPort 8771 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; if ($p) { $p | ForEach-Object { Write-Host (\"  stop PID \" + $_ + \" \" + (Get-Process -Id $_).ProcessName); Stop-Process -Id $_ -Force } } else { Write-Host \"  no server was running\" }"
timeout /t 2 /nobreak >nul
echo [2/2] Starting the new server ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable.ps1" -Mode Run
if errorlevel 1 echo ERROR: See the message above.
pause
