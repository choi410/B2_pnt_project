@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0b2-model\.venv\Scripts\python.exe" "%~dp0b2-model\bench_llamacpp.py" %*
pause
