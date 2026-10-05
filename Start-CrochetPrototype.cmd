@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\run_prototype.py
) else (
  python tools\run_prototype.py
)
if errorlevel 1 pause
