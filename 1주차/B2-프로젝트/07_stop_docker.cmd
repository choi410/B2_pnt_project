@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" docker_manage.py stop
) else (
  py -3.12 docker_manage.py stop
)
if errorlevel 1 pause
