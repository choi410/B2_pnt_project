@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable.ps1" -Mode Models
if errorlevel 1 echo ERROR: See the message above.
pause
