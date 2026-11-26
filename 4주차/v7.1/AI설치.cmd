@echo off
chcp 65001 >nul
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Run the installation script first.
    pause
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -B -X utf8 "%~dp0프로그램\setup.py" --ai
if errorlevel 1 (
    pause
    exit /b 1
)
