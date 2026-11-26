@echo off
chcp 65001 >nul
if defined PNT_INSTALL_PYTHON (
    "%PNT_INSTALL_PYTHON%" -B -X utf8 "%~dp0프로그램\setup.py"
) else (
    py -3.12 -B -X utf8 "%~dp0프로그램\setup.py"
)
if errorlevel 1 (
    echo Install Python 3.12 64-bit with the Python Launcher, then try again.
    pause
    exit /b 1
)
