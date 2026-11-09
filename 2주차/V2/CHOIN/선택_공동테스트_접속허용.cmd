@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0b2-service\work\v17\allow-team-network.ps1"
if errorlevel 1 echo ERROR: Network setup failed.
pause
