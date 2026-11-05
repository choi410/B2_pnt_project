@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if exist ".venv\Scripts\python.exe" goto existing
py -3.12 -c "import sys; assert sys.version_info[:2]==(3,12) and sys.maxsize>2**32" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys; assert sys.version_info[:2]==(3,12) and sys.maxsize>2**32" >nul 2>&1
if not errorlevel 1 goto pythonpath
echo Python 3.12 64-bit was not found.
echo Install Python 3.12 from python.org, then run this file again.
echo See 00_README.txt for instructions.
pause
exit /b 1
:existing
".venv\Scripts\python.exe" manage.py setup-web
goto result
:launcher
py -3.12 manage.py setup-web
goto result
:pythonpath
python manage.py setup-web
:result
set "B2_RESULT=%ERRORLEVEL%"
echo.
if not "%B2_RESULT%"=="0" echo Setup did not finish. Read the error above.
pause
exit /b %B2_RESULT%
