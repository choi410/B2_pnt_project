@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" manage.py check
set "B2_RESULT=%ERRORLEVEL%"
pause
exit /b %B2_RESULT%
:missing
echo Run 01_setup.cmd first. See 00_README.txt.
pause
exit /b 1
