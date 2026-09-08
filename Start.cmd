@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m bmk_studio.app %*
if errorlevel 1 pause
