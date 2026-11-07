@echo off
rem Windows launcher: double-click to start
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv && .venv\Scripts\pip install -q -r overhead_flights\app\requirements.txt )
set OF_DATA_DIR=%CD%
.venv\Scripts\python overhead_flights\app\app.py %*
