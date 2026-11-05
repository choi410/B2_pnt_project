@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" internet_share.py stop
) else (
  py -3.12 internet_share.py stop
)
if errorlevel 1 pause
