@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" internet_share.py start
) else (
  py -3.12 internet_share.py start
)
pause
