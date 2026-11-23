@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0프로그램\portable.ps1" -Mode AI
if errorlevel 1 echo ERROR: See the message above.
pause
