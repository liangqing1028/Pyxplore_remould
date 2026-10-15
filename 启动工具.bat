@echo off
chcp 65001 >nul
cd /d "%~dp0"
.venv\Scripts\python.exe -m wpem_desktop
if errorlevel 1 pause
