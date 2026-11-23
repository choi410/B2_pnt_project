@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo-run.ps1"
if errorlevel 1 echo Could not start. Check the error above.
pause
