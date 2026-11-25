@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Development copy: runs on port 8777 beside the team service (8776) and shares its AI engine.
set B2_PORT=8777
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0프로그램\portable.ps1" -Mode Run
if errorlevel 1 echo ERROR: See the message above.
if errorlevel 1 pause
