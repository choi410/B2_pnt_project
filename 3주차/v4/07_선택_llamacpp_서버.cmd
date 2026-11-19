@echo off
cd /d "%~dp0"
echo Starting llama.cpp server on http://127.0.0.1:8080 (first run downloads about 2.5GB)
llama-server -hf unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M -ngl 99 -c 8192 -np 1 --host 127.0.0.1 --port 8080
if errorlevel 1 echo ERROR: llama-server failed. Run "winget install llama.cpp" first, then open a new window.
pause
